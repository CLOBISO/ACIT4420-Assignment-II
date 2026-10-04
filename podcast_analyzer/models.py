"""Domain classes for the Podcast Voice and Recording Analyzer.

A Speaker has an AcousticProfile (their usual voice). A RecordingSession has a
Speaker and the AcousticWindow objects recorded in that session. Every class
checks its own values when it is created, so an object that exists is valid,
whoever built it.
"""

from collections import namedtuple

from .exceptions import InvalidRecordError
from .validation import (
    ALL_FEATURES,
    HIGH_NOISE_ABOVE,
    LOW_QUALITY_BELOW,
    RECORDING_FEATURES,
    SPEECH_FEATURES,
    UNRELIABLE_QUALITY_BELOW,
    check_range,
    validate_recording_id,
    validate_speaker_id,
)

STATUS_USABLE = "usable"
STATUS_NO_SPEECH = "no speech"
STATUS_UNRELIABLE = "unreliable"


class AcousticProfile:
    """A speaker's usual pitch, energy, speech rate and pause ratio."""

    FEATURES = SPEECH_FEATURES

    def __init__(self, pitch, energy, speech_rate, pause_ratio):
        # Assigning through the properties validates every value.
        self.pitch = pitch
        self.energy = energy
        self.speech_rate = speech_rate
        self.pause_ratio = pause_ratio

    @staticmethod
    def _checked(feature, value):
        return check_range(f"usual {feature}", value, feature)

    @property
    def pitch(self):
        return self._pitch

    @pitch.setter
    def pitch(self, value):
        self._pitch = self._checked("pitch", value)

    @property
    def energy(self):
        return self._energy

    @energy.setter
    def energy(self, value):
        self._energy = self._checked("energy", value)

    @property
    def speech_rate(self):
        return self._speech_rate

    @speech_rate.setter
    def speech_rate(self, value):
        self._speech_rate = self._checked("speech_rate", value)

    @property
    def pause_ratio(self):
        return self._pause_ratio

    @pause_ratio.setter
    def pause_ratio(self, value):
        self._pause_ratio = self._checked("pause_ratio", value)

    def as_dict(self):
        return {feature: getattr(self, feature) for feature in self.FEATURES}


class Speaker:
    """A podcast speaker and their usual acoustic profile (composition).

    The name is kept because it is part of the input, but no report writes it:
    the outputs identify speakers by ID only.
    """

    def __init__(self, speaker_id, name, profile):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(profile, AcousticProfile):
            raise TypeError("profile must be an AcousticProfile")
        self._speaker_id = validate_speaker_id(speaker_id)
        self._name = name.strip()
        self._profile = profile

    @property
    def speaker_id(self):
        return self._speaker_id

    @property
    def name(self):
        return self._name

    @property
    def profile(self):
        return self._profile

    def __repr__(self):
        return f"Speaker({self._speaker_id!r})"


# Where a record came from. Row numbers count the CSV header as row 1.
SourceRow = namedtuple("SourceRow", ["filename", "row_number"])


class AcousticWindow:
    """One short window of extracted features, already converted to proper types.

    features maps every name in ALL_FEATURES to a float. The four speech
    features are None when speech_present is False, because nothing was
    measured. The window decides its own status from the signal-quality rules.
    """

    def __init__(self, timestamp, speech_present, features, source):
        if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0:
            raise ValueError(f"timestamp must be a whole number of 0 or more, got {timestamp!r}")
        if not isinstance(speech_present, bool):
            raise TypeError(f"speech_present must be True or False, got {speech_present!r}")
        if not isinstance(features, dict):
            raise TypeError("features must be a dictionary")
        if not isinstance(source, SourceRow):
            raise TypeError("source must be a SourceRow")

        missing = [feature for feature in ALL_FEATURES if feature not in features]
        if missing:
            raise ValueError("features is missing: " + ", ".join(missing))
        for feature in RECORDING_FEATURES:
            check_range(feature, features[feature])
        for feature in SPEECH_FEATURES:
            if speech_present:
                check_range(feature, features[feature])
            elif features[feature] is not None:
                raise ValueError(f"{feature} must be None when speech_present is False")

        self._timestamp = timestamp
        self._speech_present = speech_present
        self._features = {feature: features[feature] for feature in ALL_FEATURES}
        self._source = source

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def speech_present(self):
        return self._speech_present

    @property
    def source(self):
        return self._source

    @property
    def status(self):
        """'no speech', 'unreliable' or 'usable'. Only usable windows describe the voice."""
        if not self._speech_present:
            return STATUS_NO_SPEECH
        if self._features["signal_quality"] < UNRELIABLE_QUALITY_BELOW:
            return STATUS_UNRELIABLE
        return STATUS_USABLE

    @property
    def exclusion_reason(self):
        """Why the window is left out of the speech analysis, or None if it is used."""
        status = self.status
        if status == STATUS_NO_SPEECH:
            return "no speech detected"
        if status == STATUS_UNRELIABLE:
            return (
                f"signal quality {self._features['signal_quality']:.2f} is below "
                f"{UNRELIABLE_QUALITY_BELOW:.2f} (unreliable)"
            )
        return None

    @property
    def warnings(self):
        """Reasons to flag a usable window. Excluded windows are not flagged."""
        if not self.is_usable:
            return ()
        warnings = []
        quality = self._features["signal_quality"]
        noise = self._features["background_noise"]
        if quality < LOW_QUALITY_BELOW:
            warnings.append(f"low signal quality {quality:.2f}")
        if noise > HIGH_NOISE_ABOVE:
            warnings.append(f"high background noise {noise:.2f}")
        return tuple(warnings)

    @property
    def is_usable(self):
        return self.status == STATUS_USABLE

    @property
    def is_flagged(self):
        return bool(self.warnings)

    def value(self, feature):
        """Return one feature value; None for a speech feature in a window without speech."""
        if feature not in self._features:
            raise KeyError(f"unknown feature {feature!r}")
        return self._features[feature]


class RecordingSession:
    """One recording by one speaker, made up of acoustic windows (composition)."""

    def __init__(self, recording_id, speaker):
        if not isinstance(speaker, Speaker):
            raise TypeError("speaker must be a Speaker")
        self._recording_id = validate_recording_id(recording_id)
        self._speaker = speaker
        # Keyed by timestamp, which makes duplicates easy to spot.
        self._windows = {}

    @property
    def recording_id(self):
        return self._recording_id

    @property
    def speaker(self):
        return self._speaker

    @property
    def windows(self):
        """All windows sorted by timestamp, as a tuple so callers cannot change them."""
        return tuple(self._windows[timestamp] for timestamp in sorted(self._windows))

    @property
    def usable_windows(self):
        return [window for window in self.windows if window.is_usable]

    @property
    def no_speech_windows(self):
        return [window for window in self.windows if window.status == STATUS_NO_SPEECH]

    @property
    def unreliable_windows(self):
        return [window for window in self.windows if window.status == STATUS_UNRELIABLE]

    @property
    def excluded_windows(self):
        return [window for window in self.windows if not window.is_usable]

    @property
    def flagged_windows(self):
        return [window for window in self.windows if window.is_flagged]

    @property
    def source_files(self):
        """Sorted names of the files this recording's rows came from."""
        return sorted({window.source.filename for window in self._windows.values()})

    def add_window(self, window):
        """Add a window; a second window with the same timestamp is rejected."""
        if not isinstance(window, AcousticWindow):
            raise TypeError("only AcousticWindow objects can be added to a session")
        existing = self._windows.get(window.timestamp)
        if existing is not None:
            first = existing.source
            raise InvalidRecordError([(
                "timestamp",
                f"duplicate timestamp {window.timestamp} in {self._recording_id} "
                f"(already on {first.filename} row {first.row_number})",
            )])
        self._windows[window.timestamp] = window

    def __len__(self):
        return len(self._windows)
