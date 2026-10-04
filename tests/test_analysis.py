"""Unit tests for podcast_analyzer.analysis.

Run from the repository root with:  python -m unittest discover -s tests -t . -v
"""

import unittest
from pathlib import Path

from podcast_analyzer.analysis import (
    Assessment,
    QualityAssessment,
    SessionAnalyzer,
    StyleAssessment,
    coefficient_of_variation,
    round_for_display,
    summarise_feature,
)
from podcast_analyzer.loader import load_recordings, load_speakers
from podcast_analyzer.models import (
    AcousticProfile,
    AcousticWindow,
    RecordingSession,
    SourceRow,
    Speaker,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

SPEAKER = Speaker(
    "S001", "Test Speaker",
    AcousticProfile(pitch=150.0, energy=0.40, speech_rate=120.0, pause_ratio=0.25),
)
NO_SPEECH = {"pitch": None, "energy": None, "speech_rate": None, "pause_ratio": None}


def make_window(timestamp=0, speech_present=True, **changes):
    """A valid window matching SPEAKER's profile, with optional changes."""
    features = {
        "pitch": 150.0, "energy": 0.40, "speech_rate": 120.0, "pause_ratio": 0.25,
        "background_noise": 0.10, "signal_quality": 0.92,
    }
    features.update(changes)
    if not speech_present:
        features.update(NO_SPEECH)
    return AcousticWindow(timestamp, speech_present, features, SourceRow("test.csv", timestamp + 2))


def make_session(windows):
    session = RecordingSession("REC-2026-001", SPEAKER)
    for window in windows:
        session.add_window(window)
    return session


def analyze(windows):
    return SessionAnalyzer().analyze(make_session(windows))


class CalculationTests(unittest.TestCase):
    def test_summary_of_known_values(self):
        stats = summarise_feature([2, 4, 4, 4, 5, 5, 7, 9])
        self.assertEqual(stats["count"], 8)
        self.assertEqual(stats["mean"], 5)
        self.assertEqual(stats["min"], 2)
        self.assertEqual(stats["max"], 9)
        self.assertAlmostEqual(stats["stdev"], 2.138, places=3)

    def test_summary_of_empty_and_single_value(self):
        self.assertIsNone(summarise_feature([]))
        self.assertEqual(summarise_feature([3.5])["stdev"], 0.0)

    def test_coefficient_of_variation(self):
        self.assertAlmostEqual(coefficient_of_variation({"mean": 100, "stdev": 8}), 0.08)
        self.assertEqual(coefficient_of_variation(None), 0.0)
        self.assertEqual(coefficient_of_variation({"mean": 0, "stdev": 1}), 0.0)

    def test_round_for_display_removes_negative_zero(self):
        self.assertEqual(f"{round_for_display(-0.001, 2):+.2f}", "+0.00")

    def test_noise_and_quality_use_windows_without_speech(self):
        windows = [make_window(i) for i in range(3)]
        windows.append(make_window(3, speech_present=False, background_noise=0.50))
        summary = analyze(windows)["summary"]
        self.assertEqual(summary["pitch"]["count"], 3)
        self.assertEqual(summary["background_noise"]["count"], 4)
        self.assertEqual(summary["signal_quality"]["count"], 4)

    def test_unreliable_windows_count_for_noise_but_not_for_speech(self):
        windows = [make_window(i) for i in range(3)]
        windows.append(make_window(3, signal_quality=0.20, pitch=300.0))
        summary = analyze(windows)["summary"]
        self.assertEqual(summary["pitch"]["count"], 3)
        self.assertEqual(summary["pitch"]["max"], 150.0)
        self.assertEqual(summary["signal_quality"]["count"], 4)
        self.assertEqual(summary["signal_quality"]["min"], 0.20)

    def test_comparison_with_profile(self):
        windows = [make_window(i, energy=0.55, speech_rate=135.0) for i in range(4)]
        comparison = analyze(windows)["comparison"]
        self.assertAlmostEqual(comparison["energy"]["difference"], 0.15)
        self.assertAlmostEqual(comparison["speech_rate"]["percent"], 12.5)
        self.assertEqual(comparison["pitch"]["usual"], 150.0)

    def test_window_counts(self):
        windows = [
            make_window(0),
            make_window(1, signal_quality=0.5),
            make_window(2, speech_present=False),
            make_window(3, signal_quality=0.2),
        ]
        self.assertEqual(
            analyze(windows)["windows"],
            {"total": 4, "usable": 2, "no_speech": 1, "unreliable": 1, "flagged": 1},
        )


class StyleRuleTests(unittest.TestCase):
    def label(self, windows):
        return analyze(windows)["style"]["label"]

    def test_consistent(self):
        self.assertEqual(self.label([make_window(i) for i in range(6)]), "consistent")

    def test_energetic(self):
        windows = [make_window(i, energy=0.55, speech_rate=135.0) for i in range(6)]
        self.assertEqual(self.label(windows), "energetic")

    def test_energy_alone_is_not_energetic(self):
        windows = [make_window(i, energy=0.55) for i in range(6)]
        self.assertEqual(self.label(windows), "consistent")

    def test_deliberate(self):
        windows = [make_window(i, speech_rate=100.0, pause_ratio=0.35) for i in range(6)]
        self.assertEqual(self.label(windows), "deliberate")

    def test_noise_affected(self):
        windows = [make_window(i, background_noise=0.8) for i in range(6)]
        self.assertEqual(self.label(windows), "noise affected")

    def test_temporarily_varied(self):
        windows = [make_window(i) for i in range(6)]
        windows += [make_window(i, energy=0.70, pitch=190.0) for i in range(6, 9)]
        self.assertEqual(self.label(windows), "temporarily varied")

    def test_insufficient_data_when_too_few_windows(self):
        self.assertEqual(self.label([make_window(0), make_window(1)]), "insufficient data")

    def test_three_usable_windows_are_enough(self):
        self.assertEqual(self.label([make_window(i) for i in range(3)]), "consistent")

    def test_insufficient_data_when_under_half_usable(self):
        windows = [make_window(i) for i in range(3)]
        windows += [make_window(i, speech_present=False) for i in range(3, 7)]
        self.assertEqual(self.label(windows), "insufficient data")

    def test_exactly_half_usable_is_enough(self):
        windows = [make_window(i) for i in range(3)]
        windows += [make_window(i, speech_present=False) for i in range(3, 6)]
        self.assertEqual(self.label(windows), "consistent")

    def test_empty_session_does_not_crash(self):
        result = analyze([])
        self.assertEqual(result["style"]["label"], "insufficient data")
        self.assertEqual(result["windows"]["total"], 0)
        self.assertIsNone(result["summary"]["pitch"])
        self.assertIsNone(result["summary"]["background_noise"])
        self.assertEqual(result["status"], "insufficient data")

    def test_session_of_only_no_speech_windows(self):
        result = analyze([make_window(i, speech_present=False) for i in range(5)])
        self.assertEqual(result["style"]["label"], "insufficient data")
        self.assertIsNone(result["summary"]["pitch"])
        self.assertEqual(result["summary"]["background_noise"]["count"], 5)
        self.assertEqual(result["comparison"]["pitch"]["session"], None)

    def test_session_of_only_unreliable_windows(self):
        result = analyze([make_window(i, signal_quality=0.1) for i in range(5)])
        self.assertEqual(result["style"]["label"], "insufficient data")
        self.assertEqual(result["windows"]["unreliable"], 5)

    def test_single_usable_window(self):
        self.assertEqual(self.label([make_window(0)]), "insufficient data")

    def test_insufficient_data_reason_names_the_counts(self):
        reasons = analyze([make_window(0), make_window(1)])["style"]["reasons"]
        self.assertIn("only 2 of 2 windows are usable", reasons[0])

    def test_insufficient_data_reason_for_one_window_is_singular(self):
        reasons = analyze([make_window(0)])["style"]["reasons"]
        self.assertIn("only 1 of 1 window is usable", reasons[0])


class QualityTests(unittest.TestCase):
    def test_score_formula(self):
        self.assertEqual(QualityAssessment.score(1.0, 0.0, 1.0), 100.0)
        self.assertEqual(QualityAssessment.score(0.0, 1.0, 0.0), 0.0)
        self.assertEqual(QualityAssessment.score(0.8, 0.2, 0.5), 74.0)

    def test_clean_recording_is_good(self):
        result = analyze([make_window(i) for i in range(6)])
        self.assertEqual(result["quality"]["label"], "good")
        self.assertGreaterEqual(result["quality"]["score"], 75)

    def test_poor_recording(self):
        windows = [make_window(i, signal_quality=0.40, background_noise=0.90) for i in range(6)]
        result = analyze(windows)
        self.assertEqual(result["quality"]["label"], "poor")
        self.assertLess(result["quality"]["score"], 55)

    def test_good_is_capped_when_most_windows_unusable(self):
        windows = [make_window(i) for i in range(3)]
        windows += [make_window(i, speech_present=False) for i in range(3, 10)]
        quality = analyze(windows)["quality"]
        self.assertEqual(quality["label"], "acceptable")
        self.assertTrue(any("capped" in reason for reason in quality["reasons"]))

    def test_empty_session_cannot_be_evaluated(self):
        quality = analyze([])["quality"]
        self.assertEqual(quality["label"], "cannot be evaluated")
        self.assertIsNone(quality["score"])

    def test_fewer_than_three_windows_give_insufficient_data(self):
        for count, reason in (
            (1, "only 1 window; at least 3 are needed for a quality score"),
            (2, "only 2 windows; at least 3 are needed for a quality score"),
        ):
            with self.subTest(count=count):
                quality = analyze([make_window(i) for i in range(count)])["quality"]
                self.assertEqual(quality["label"], "insufficient data")
                self.assertIsNone(quality["score"])
                self.assertEqual(quality["reasons"], [reason])

    def test_three_windows_are_enough_for_a_score(self):
        quality = analyze([make_window(i) for i in range(3)])["quality"]
        self.assertEqual(quality["label"], "good")
        self.assertIsNotNone(quality["score"])

    def test_minimum_counts_all_windows_not_only_usable_ones(self):
        windows = [make_window(0), make_window(1, speech_present=False), make_window(2, signal_quality=0.2)]
        self.assertIsNotNone(analyze(windows)["quality"]["score"])

    def test_flagged_windows_are_mentioned(self):
        windows = [make_window(i) for i in range(4)] + [make_window(4, signal_quality=0.5)]
        reasons = analyze(windows)["quality"]["reasons"]
        self.assertTrue(any("1 usable window(s) flagged" in reason for reason in reasons))


class AnalyzerTests(unittest.TestCase):
    def test_result_has_required_keys_and_counts_add_up(self):
        windows = [make_window(0), make_window(1, speech_present=False), make_window(2, signal_quality=0.1)]
        result = analyze(windows)
        for key in ("recording_id", "speaker_id", "source_files", "windows", "excluded", "warnings",
                    "summary", "comparison", "style", "quality", "status"):
            self.assertIn(key, result)
        self.assertEqual(result["recording_id"], "REC-2026-001")
        self.assertEqual(result["speaker_id"], "S001")
        self.assertEqual(result["source_files"], ["test.csv"])
        counts = result["windows"]
        self.assertEqual(counts["usable"] + counts["no_speech"] + counts["unreliable"], counts["total"])
        self.assertEqual(
            [(e["timestamp"], e["status"]) for e in result["excluded"]],
            [(1, "no speech"), (2, "unreliable")],
        )

    def test_warnings_list_flagged_windows(self):
        result = analyze([make_window(0), make_window(1, signal_quality=0.5, background_noise=0.7)])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["warnings"][0]["timestamp"], 1)
        self.assertEqual(len(result["warnings"][0]["warnings"]), 2)

    def test_status_analysed_versus_insufficient(self):
        self.assertEqual(analyze([make_window(i) for i in range(4)])["status"], "analysed")
        self.assertEqual(analyze([make_window(0)])["status"], "insufficient data")

    def test_noise_affected_is_still_analysed(self):
        windows = [make_window(i, background_noise=0.8) for i in range(6)]
        result = analyze(windows)
        self.assertEqual(result["style"]["label"], "noise affected")
        self.assertEqual(result["status"], "analysed")

    def test_base_assessment_must_be_overridden(self):
        with self.assertRaises(NotImplementedError):
            Assessment().evaluate({}, {}, {})

    def test_analyzer_rejects_non_assessments(self):
        with self.assertRaises(TypeError):
            SessionAnalyzer(["style"])

    def test_assessments_are_polymorphic(self):
        result = SessionAnalyzer([StyleAssessment()]).analyze(make_session([make_window(i) for i in range(4)]))
        self.assertIn("style", result)
        self.assertNotIn("quality", result)
        self.assertEqual(result["status"], "analysed")

    def test_analyze_all_is_sorted_by_recording_id(self):
        first = RecordingSession("REC-2026-002", SPEAKER)
        second = RecordingSession("REC-2026-001", SPEAKER)
        results = SessionAnalyzer().analyze_all({"REC-2026-002": first, "REC-2026-001": second})
        self.assertEqual([r["recording_id"] for r in results], ["REC-2026-001", "REC-2026-002"])


class OfficialDataTests(unittest.TestCase):
    EXPECTED = {
        "REC-2026-001": "consistent",
        "REC-2026-002": "energetic",
        "REC-2026-003": "deliberate",
        "REC-2026-004": "noise affected",
        "REC-2026-005": "insufficient data",
        "REC-2026-101": "insufficient data",
    }

    @classmethod
    def setUpClass(cls):
        speakers, _ = load_speakers(DATA_DIR / "speakers.csv")
        loaded = load_recordings(
            [DATA_DIR / "recording_sessions.csv", DATA_DIR / "recording_sessions_invalid.csv"], speakers
        )
        cls.results = {r["recording_id"]: r for r in SessionAnalyzer().analyze_all(loaded.sessions)}

    def test_expected_style_labels(self):
        self.assertEqual({rid: r["style"]["label"] for rid, r in self.results.items()}, self.EXPECTED)

    def test_expected_status(self):
        for recording_id, label in self.EXPECTED.items():
            with self.subTest(recording_id=recording_id):
                expected = "insufficient data" if label == "insufficient data" else "analysed"
                self.assertEqual(self.results[recording_id]["status"], expected)

    def test_noise_affected_recording_scores_acceptable(self):
        quality = self.results["REC-2026-004"]["quality"]
        self.assertEqual(quality["label"], "acceptable")
        self.assertEqual(quality["score"], 64.3)

    def test_recording_005_has_three_no_speech_windows(self):
        counts = self.results["REC-2026-005"]["windows"]
        self.assertEqual((counts["total"], counts["usable"], counts["no_speech"]), (5, 2, 3))
        self.assertEqual(counts["unreliable"], 0)

    def test_expected_quality(self):
        expected = {
            "REC-2026-001": ("good", 96.3),
            "REC-2026-002": ("good", 94.7),
            "REC-2026-003": ("good", 96.0),
            "REC-2026-004": ("acceptable", 64.3),
            "REC-2026-005": ("acceptable", 69.0),
            "REC-2026-101": ("insufficient data", None),
        }
        actual = {rid: (r["quality"]["label"], r["quality"]["score"]) for rid, r in self.results.items()}
        self.assertEqual(actual, expected)

    def test_single_window_recording_has_no_quality_score(self):
        quality = self.results["REC-2026-101"]["quality"]
        self.assertEqual(quality["reasons"], ["only 1 window; at least 3 are needed for a quality score"])


class ExtraFixtureTests(unittest.TestCase):
    """tests/fixtures/recording_sessions_extra.csv together with the official speakers.csv."""

    @classmethod
    def setUpClass(cls):
        speakers, _ = load_speakers(DATA_DIR / "speakers.csv")
        loaded = load_recordings([FIXTURE_DIR / "recording_sessions_extra.csv"], speakers)
        cls.results = {r["recording_id"]: r for r in SessionAnalyzer().analyze_all(loaded.sessions)}

    def test_pitch_burst_is_temporarily_varied(self):
        result = self.results["REC-2026-201"]
        self.assertEqual(result["style"]["label"], "temporarily varied")
        self.assertEqual(result["status"], "analysed")
        self.assertGreater(coefficient_of_variation(result["summary"]["pitch"]), StyleAssessment.PITCH_CV_LIMIT)
        # Only the pitch varies; the other speech features stay calm.
        self.assertLessEqual(result["summary"]["energy"]["stdev"], StyleAssessment.ENERGY_STDEV_LIMIT)
        self.assertLessEqual(
            coefficient_of_variation(result["summary"]["speech_rate"]), StyleAssessment.RATE_CV_LIMIT
        )
        self.assertTrue(result["style"]["reasons"][0].startswith("pitch varies by"))
        self.assertEqual(result["windows"]["usable"], 6)

    def test_unreliable_windows_leave_too_little_speech(self):
        result = self.results["REC-2026-202"]
        self.assertEqual(
            result["windows"], {"total": 5, "usable": 2, "no_speech": 0, "unreliable": 3, "flagged": 0}
        )
        self.assertEqual([e["timestamp"] for e in result["excluded"]], [1, 2, 3])
        self.assertTrue(all(e["status"] == "unreliable" for e in result["excluded"]))
        self.assertEqual(result["style"]["label"], "insufficient data")
        self.assertIn("only 2 of 5 windows are usable", result["style"]["reasons"][0])
        self.assertEqual(result["status"], "insufficient data")

    def test_five_windows_are_enough_for_a_quality_score(self):
        quality = self.results["REC-2026-202"]["quality"]
        self.assertEqual(quality["label"], "acceptable")
        self.assertEqual(quality["score"], 61.7)


if __name__ == "__main__":
    unittest.main()
