"""Calculations and the assessments that interpret a recording session.

This module does not import models.py. The functions work on any object that
offers the same attributes as RecordingSession (duck typing), so the
calculations can be tested with simple stand-in objects.
"""

import statistics

from .validation import RECORDING_FEATURES, SPEECH_FEATURES

STATUS_ANALYSED = "analysed"
STATUS_INSUFFICIENT = "insufficient data"


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------

def round_for_display(value, digits):
    """Round a value for display and turn -0.0 into 0.0, so reports never show '-0.00'."""
    return round(value, digits) + 0.0


def summarise_feature(values):
    """Return count, mean, min, max and sample standard deviation, or None for no values."""
    if not values:
        return None
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def coefficient_of_variation(stats):
    """Return stdev / mean: spread relative to the size of the values."""
    if not stats or stats["mean"] == 0:
        return 0.0
    return stats["stdev"] / stats["mean"]


def summarise_session(session):
    """Summarise all six features of a session.

    Speech features use usable windows only. Noise and signal quality describe
    the whole recording, so they use every accepted window, including windows
    without speech and unreliable ones.
    """
    summary = {}
    usable = session.usable_windows
    for feature in SPEECH_FEATURES:
        summary[feature] = summarise_feature([window.value(feature) for window in usable])
    for feature in RECORDING_FEATURES:
        values = [window.value(feature) for window in session.windows]
        summary[feature] = summarise_feature([value for value in values if value is not None])
    return summary


def compare_with_profile(summary, profile):
    """Compare each speech feature's session mean with the speaker's usual value."""
    comparison = {}
    for feature in SPEECH_FEATURES:
        usual = getattr(profile, feature)
        stats = summary.get(feature)
        if stats is None:
            comparison[feature] = {"session": None, "usual": usual, "difference": None, "percent": None}
            continue
        difference = stats["mean"] - usual
        comparison[feature] = {
            "session": stats["mean"],
            "usual": usual,
            "difference": difference,
            "percent": difference / usual * 100 if usual else None,
        }
    return comparison


def count_windows(session):
    """Count total, usable, no-speech, unreliable and flagged windows."""
    return {
        "total": len(session.windows),
        "usable": len(session.usable_windows),
        "no_speech": len(session.no_speech_windows),
        "unreliable": len(session.unreliable_windows),
        "flagged": len(session.flagged_windows),
    }


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------

class Assessment:
    """Base class for one way of interpreting an analysed session.

    Subclasses override `name` and `evaluate`. SessionAnalyzer calls every
    assessment the same way, so a new assessment can be added without changing
    the analyzer.
    """

    name = "assessment"

    def evaluate(self, summary, comparison, counts):
        """Return a dictionary with at least 'label' and 'reasons'."""
        raise NotImplementedError("subclasses must implement evaluate()")

    def _result(self, label, reasons, **extra):
        result = {"label": label, "reasons": list(reasons)}
        result.update(extra)
        return result

    def __str__(self):
        return f"{type(self).__name__} ({self.name})"


class StyleAssessment(Assessment):
    """Describes the speaking style. The first matching rule wins."""

    name = "style"

    MIN_USABLE_WINDOWS = 3
    MIN_USABLE_SHARE = 0.5
    NOISE_MEAN_LIMIT = 0.50
    QUALITY_MEAN_LIMIT = 0.70
    PITCH_CV_LIMIT = 0.08
    RATE_CV_LIMIT = 0.12
    ENERGY_STDEV_LIMIT = 0.08
    ENERGETIC_ENERGY_RISE = 0.10
    ENERGETIC_RATE_RISE_PCT = 10
    ENERGETIC_PITCH_RISE_PCT = 7
    DELIBERATE_RATE_DROP_PCT = -12
    DELIBERATE_PAUSE_RISE = 0.08

    def evaluate(self, summary, comparison, counts):
        total, usable = counts["total"], counts["usable"]
        # usable is checked first, so an empty session never reaches the division.
        if usable < self.MIN_USABLE_WINDOWS or usable / total < self.MIN_USABLE_SHARE:
            windows = "window is" if total == 1 else "windows are"
            return self._result(STATUS_INSUFFICIENT, [
                f"only {usable} of {total} {windows} usable; at least "
                f"{self.MIN_USABLE_WINDOWS} and at least {self.MIN_USABLE_SHARE:.0%} are needed",
            ])

        noise_reasons = self._noise_reasons(summary)
        if noise_reasons:
            noise_reasons.append("noise raises measured energy and pitch, so speaking style is not judged")
            return self._result("noise affected", noise_reasons)

        variation_reasons = self._variation_reasons(summary)
        if variation_reasons:
            return self._result("temporarily varied", variation_reasons)

        energy = round_for_display(comparison["energy"]["difference"], 2)
        rate = round_for_display(comparison["speech_rate"]["percent"], 1)
        pitch = round_for_display(comparison["pitch"]["percent"], 1)
        pause = round_for_display(comparison["pause_ratio"]["difference"], 2)

        if energy >= self.ENERGETIC_ENERGY_RISE and (
            rate >= self.ENERGETIC_RATE_RISE_PCT or pitch >= self.ENERGETIC_PITCH_RISE_PCT
        ):
            return self._result("energetic", [
                f"energy is {energy:+.2f} above usual (threshold +{self.ENERGETIC_ENERGY_RISE:.2f})",
                f"speech rate is {rate:+.1f}% vs usual (threshold +{self.ENERGETIC_RATE_RISE_PCT}%)",
                f"pitch is {pitch:+.1f}% vs usual (threshold +{self.ENERGETIC_PITCH_RISE_PCT}%)",
                "energetic needs the energy rise plus a faster rate or a higher pitch",
            ])

        if rate <= self.DELIBERATE_RATE_DROP_PCT and pause >= self.DELIBERATE_PAUSE_RISE:
            return self._result("deliberate", [
                f"speech rate is {rate:+.1f}% vs usual (threshold {self.DELIBERATE_RATE_DROP_PCT}%)",
                f"pause ratio is {pause:+.2f} vs usual (threshold +{self.DELIBERATE_PAUSE_RISE:.2f})",
            ])

        return self._result("consistent", [
            "all speech features stay within the thresholds of the usual profile",
            f"pitch {pitch:+.1f}%, energy {energy:+.2f}, speech rate {rate:+.1f}%, pause ratio {pause:+.2f}",
        ])

    def _noise_reasons(self, summary):
        reasons = []
        noise = summary["background_noise"]
        quality = summary["signal_quality"]
        if noise and noise["mean"] >= self.NOISE_MEAN_LIMIT:
            reasons.append(
                f"average background noise {noise['mean']:.2f} is at or above {self.NOISE_MEAN_LIMIT:.2f}"
            )
        if quality and quality["mean"] < self.QUALITY_MEAN_LIMIT:
            reasons.append(
                f"average signal quality {quality['mean']:.2f} is below {self.QUALITY_MEAN_LIMIT:.2f}"
            )
        return reasons

    def _variation_reasons(self, summary):
        reasons = []
        pitch_cv = coefficient_of_variation(summary["pitch"])
        rate_cv = coefficient_of_variation(summary["speech_rate"])
        energy_stdev = summary["energy"]["stdev"]
        if pitch_cv > self.PITCH_CV_LIMIT:
            reasons.append(f"pitch varies by {pitch_cv:.1%} around its mean (limit {self.PITCH_CV_LIMIT:.0%})")
        if rate_cv > self.RATE_CV_LIMIT:
            reasons.append(f"speech rate varies by {rate_cv:.1%} around its mean (limit {self.RATE_CV_LIMIT:.0%})")
        if energy_stdev > self.ENERGY_STDEV_LIMIT:
            reasons.append(
                f"energy standard deviation {energy_stdev:.2f} is above {self.ENERGY_STDEV_LIMIT:.2f}"
            )
        if reasons:
            reasons.append("the style changes within the session instead of shifting as a whole")
        return reasons


class QualityAssessment(Assessment):
    """Scores overall recording quality from 0 to 100."""

    name = "quality"

    QUALITY_WEIGHT = 0.5
    LOW_NOISE_WEIGHT = 0.3
    USABLE_WEIGHT = 0.2
    BANDS = ((75, "good"), (55, "acceptable"), (0, "poor"))
    # A recording where most windows are unusable cannot be called good,
    # however clean the remaining windows sound.
    MIN_USABLE_SHARE_FOR_GOOD = 0.5
    # One or two windows are a snapshot, not a recording: a single clean
    # window would otherwise score "good". Same minimum as the style rules.
    MIN_WINDOWS_FOR_SCORE = 3

    @staticmethod
    def score(mean_quality, mean_noise, usable_share):
        """Combine three 0-1 inputs into a 0-100 score.

        A staticmethod: the formula belongs to this assessment but needs no
        instance state, and tests can call it directly.
        """
        weighted = (
            QualityAssessment.QUALITY_WEIGHT * mean_quality
            + QualityAssessment.LOW_NOISE_WEIGHT * (1 - mean_noise)
            + QualityAssessment.USABLE_WEIGHT * usable_share
        )
        return round(100 * weighted, 1)

    def evaluate(self, summary, comparison, counts):
        quality = summary["signal_quality"]
        noise = summary["background_noise"]
        if quality is None or noise is None:
            return self._result(
                "cannot be evaluated",
                ["no valid signal-quality or background-noise measurements"],
                score=None,
            )
        # Checked after the measurements: an empty session has no values at
        # all, which "cannot be evaluated" describes better.
        total = counts["total"]
        if total < self.MIN_WINDOWS_FOR_SCORE:
            windows = "window" if total == 1 else "windows"
            return self._result(
                STATUS_INSUFFICIENT,
                [f"only {total} {windows}; at least {self.MIN_WINDOWS_FOR_SCORE} are needed for a quality score"],
                score=None,
            )

        usable_share = counts["usable"] / total
        score = self.score(quality["mean"], noise["mean"], usable_share)
        label = next(name for limit, name in self.BANDS if score >= limit)

        reasons = [
            f"average signal quality {quality['mean']:.2f} (50% of the score)",
            f"average background noise {noise['mean']:.2f} (30% of the score, lower is better)",
            f"{counts['usable']} of {counts['total']} windows usable (20% of the score)",
        ]
        if counts["flagged"]:
            reasons.append(f"{counts['flagged']} usable window(s) flagged for low quality or high noise")
        reasons.append(f"{score} is in the '{label}' band (good >= 75, acceptable >= 55, otherwise poor)")
        if label == "good" and usable_share < self.MIN_USABLE_SHARE_FOR_GOOD:
            label = "acceptable"
            reasons.append(
                f"capped at 'acceptable' because fewer than {self.MIN_USABLE_SHARE_FOR_GOOD:.0%} "
                "of the windows are usable"
            )
        return self._result(label, reasons, score=score)


class SessionAnalyzer:
    """Runs the calculations and every assessment on a RecordingSession."""

    def __init__(self, assessments=None):
        if assessments is None:
            assessments = [StyleAssessment(), QualityAssessment()]
        for assessment in assessments:
            if not isinstance(assessment, Assessment):
                raise TypeError(f"{assessment!r} is not an Assessment")
        self._assessments = list(assessments)

    def analyze(self, session):
        """Return the structured result dictionary for one session."""
        counts = count_windows(session)
        summary = summarise_session(session)
        comparison = compare_with_profile(summary, session.speaker.profile)

        result = {
            "recording_id": session.recording_id,
            "speaker_id": session.speaker.speaker_id,
            "source_files": list(session.source_files),
            "windows": counts,
            "excluded": [
                {"timestamp": window.timestamp, "status": window.status, "reason": window.exclusion_reason}
                for window in session.excluded_windows
            ],
            "warnings": [
                {"timestamp": window.timestamp, "warnings": list(window.warnings)}
                for window in session.flagged_windows
            ],
            "summary": summary,
            "comparison": comparison,
        }
        for assessment in self._assessments:
            result[assessment.name] = assessment.evaluate(summary, comparison, counts)
        # Keeps "not enough usable data" apart from a real normal/unusual result.
        style_label = result.get("style", {}).get("label")
        result["status"] = STATUS_INSUFFICIENT if style_label == STATUS_INSUFFICIENT else STATUS_ANALYSED
        return result

    def analyze_all(self, sessions):
        """Analyse a dict of recording_id -> session and return the results sorted by recording_id."""
        return [self.analyze(sessions[recording_id]) for recording_id in sorted(sessions)]
