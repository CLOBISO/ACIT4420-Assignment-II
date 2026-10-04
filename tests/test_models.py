"""Unit tests for podcast_analyzer.models.

Run from the repository root with:  python -m unittest discover -s tests -t . -v
"""

import unittest

from podcast_analyzer.exceptions import InvalidIdentifierError, InvalidRecordError
from podcast_analyzer.models import (
    AcousticProfile,
    AcousticWindow,
    RecordingSession,
    SourceRow,
    Speaker,
)


def make_profile(**changes):
    values = {"pitch": 150.0, "energy": 0.40, "speech_rate": 120.0, "pause_ratio": 0.25}
    values.update(changes)
    return AcousticProfile(**values)


def make_speaker(speaker_id="S001"):
    return Speaker(speaker_id, "Test Speaker", make_profile())


def make_features(**changes):
    features = {
        "pitch": 150.0, "energy": 0.40, "speech_rate": 120.0, "pause_ratio": 0.25,
        "background_noise": 0.10, "signal_quality": 0.92,
    }
    features.update(changes)
    return features


def make_window(timestamp=0, row=2, speech_present=True, filename="test.csv", **changes):
    """A valid window; speech features are None when speech_present is False."""
    features = make_features(**changes)
    if not speech_present:
        features.update(pitch=None, energy=None, speech_rate=None, pause_ratio=None)
    return AcousticWindow(timestamp, speech_present, features, SourceRow(filename, row))


class AcousticProfileTests(unittest.TestCase):
    def test_values_are_stored(self):
        self.assertEqual(make_profile().as_dict(), {
            "pitch": 150.0, "energy": 0.40, "speech_rate": 120.0, "pause_ratio": 0.25,
        })

    def test_setter_protects_profile(self):
        profile = make_profile()
        for feature, bad in (("pitch", 10), ("energy", 1.5), ("speech_rate", 300), ("pause_ratio", -0.1)):
            with self.subTest(feature=feature):
                with self.assertRaises(ValueError):
                    setattr(profile, feature, bad)
        self.assertEqual(profile.energy, 0.40)

    def test_setter_accepts_valid_value(self):
        profile = make_profile()
        profile.energy = 0.55
        self.assertEqual(profile.energy, 0.55)

    def test_invalid_constructor_value_raises(self):
        with self.assertRaises(ValueError):
            make_profile(pitch=500)


class SpeakerTests(unittest.TestCase):
    def test_valid_speaker(self):
        speaker = Speaker(" S002 ", "  Name ", make_profile())
        self.assertEqual(speaker.speaker_id, "S002")
        self.assertEqual(speaker.name, "Name")
        self.assertIsInstance(speaker.profile, AcousticProfile)

    def test_invalid_id_raises(self):
        with self.assertRaises(InvalidIdentifierError):
            Speaker("001", "Name", make_profile())

    def test_empty_name_raises(self):
        for name in ("", "   ", None):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    Speaker("S001", name, make_profile())

    def test_profile_must_be_a_profile(self):
        with self.assertRaises(TypeError):
            Speaker("S001", "Name", {"pitch": 150})

    def test_repr_has_no_name(self):
        self.assertNotIn("Test Speaker", repr(make_speaker()))

    def test_properties_are_read_only(self):
        with self.assertRaises(AttributeError):
            make_speaker().speaker_id = "S002"


class AcousticWindowTests(unittest.TestCase):
    def test_window_with_good_signal_is_usable(self):
        window = make_window()
        self.assertEqual(window.status, "usable")
        self.assertTrue(window.is_usable)
        self.assertFalse(window.is_flagged)
        self.assertIsNone(window.exclusion_reason)
        self.assertEqual(window.value("pitch"), 150.0)

    def test_window_without_speech(self):
        window = make_window(speech_present=False)
        self.assertEqual(window.status, "no speech")
        self.assertFalse(window.is_usable)
        self.assertEqual(window.warnings, ())
        self.assertIsNone(window.value("pitch"))
        self.assertEqual(window.exclusion_reason, "no speech detected")

    def test_unreliable_boundary_at_035(self):
        for quality, status in ((0.34, "unreliable"), (0.35, "usable"), (0.0, "unreliable")):
            with self.subTest(quality=quality):
                self.assertEqual(make_window(signal_quality=quality).status, status)

    def test_unreliable_window_is_not_flagged(self):
        window = make_window(signal_quality=0.2)
        self.assertFalse(window.is_usable)
        self.assertEqual(window.warnings, ())
        self.assertIn("unreliable", window.exclusion_reason)

    def test_low_quality_warning_boundary_at_060(self):
        self.assertEqual(make_window(signal_quality=0.60).warnings, ())
        self.assertEqual(make_window(signal_quality=0.59).warnings, ("low signal quality 0.59",))
        self.assertTrue(make_window(signal_quality=0.59).is_flagged)

    def test_high_noise_warning_boundary_at_060(self):
        self.assertEqual(make_window(background_noise=0.60).warnings, ())
        self.assertEqual(make_window(background_noise=0.61).warnings, ("high background noise 0.61",))

    def test_both_warnings_together(self):
        window = make_window(signal_quality=0.5, background_noise=0.8)
        self.assertEqual(len(window.warnings), 2)

    def test_constructor_validation(self):
        source = SourceRow("t.csv", 2)
        features = make_features()
        with self.assertRaises(ValueError):
            AcousticWindow(-1, True, features, source)
        with self.assertRaises(ValueError):
            AcousticWindow(True, True, features, source)
        with self.assertRaises(TypeError):
            AcousticWindow(0, "yes", features, source)
        with self.assertRaises(TypeError):
            AcousticWindow(0, True, features, ("t.csv", 2))
        with self.assertRaises(ValueError):
            AcousticWindow(0, True, {"pitch": 150.0}, source)
        with self.assertRaises(ValueError):
            make_window(pitch=500)
        with self.assertRaises(ValueError):
            make_window(signal_quality=1.1)

    def test_speech_features_must_be_none_without_speech(self):
        with self.assertRaises(ValueError):
            AcousticWindow(0, False, make_features(), SourceRow("t.csv", 2))

    def test_unknown_feature_raises_key_error(self):
        with self.assertRaises(KeyError):
            make_window().value("tempo")


class RecordingSessionTests(unittest.TestCase):
    def setUp(self):
        self.session = RecordingSession("REC-2026-001", make_speaker())

    def test_invalid_recording_id_raises(self):
        with self.assertRaises(InvalidIdentifierError):
            RecordingSession("REC-26-1", make_speaker())

    def test_session_needs_a_speaker(self):
        with self.assertRaises(TypeError):
            RecordingSession("REC-2026-001", "S001")

    def test_windows_are_a_read_only_tuple_sorted_by_timestamp(self):
        self.session.add_window(make_window(5))
        self.session.add_window(make_window(1))
        self.assertIsInstance(self.session.windows, tuple)
        self.assertEqual([w.timestamp for w in self.session.windows], [1, 5])
        self.assertEqual(len(self.session), 2)

    def test_only_windows_can_be_added(self):
        with self.assertRaises(TypeError):
            self.session.add_window({"timestamp": 0})

    def test_duplicate_timestamp_raises_invalid_record_error(self):
        self.session.add_window(make_window(3, row=4))
        with self.assertRaises(InvalidRecordError) as context:
            self.session.add_window(make_window(3, row=9))
        field, reason = context.exception.problems[0]
        self.assertEqual(field, "timestamp")
        self.assertIn("duplicate timestamp 3 in REC-2026-001", reason)
        self.assertEqual(len(self.session), 1)

    def test_window_groups(self):
        self.session.add_window(make_window(0))
        self.session.add_window(make_window(1, speech_present=False))
        self.session.add_window(make_window(2, signal_quality=0.2))
        self.session.add_window(make_window(3, signal_quality=0.5))
        self.assertEqual([w.timestamp for w in self.session.usable_windows], [0, 3])
        self.assertEqual([w.timestamp for w in self.session.no_speech_windows], [1])
        self.assertEqual([w.timestamp for w in self.session.unreliable_windows], [2])
        self.assertEqual([w.timestamp for w in self.session.excluded_windows], [1, 2])
        self.assertEqual([w.timestamp for w in self.session.flagged_windows], [3])

    def test_source_files_are_sorted_and_unique(self):
        self.session.add_window(make_window(0))
        self.session.add_window(make_window(1, filename="a.csv"))
        self.session.add_window(make_window(2, filename="a.csv"))
        self.assertEqual(self.session.source_files, ["a.csv", "test.csv"])


if __name__ == "__main__":
    unittest.main()
