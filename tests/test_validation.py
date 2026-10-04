"""Unit tests for podcast_analyzer.validation.

Run from the repository root with:  python -m unittest discover -s tests -t . -v
"""

import math
import unittest
from pathlib import Path

from podcast_analyzer.exceptions import DataFileError, InvalidIdentifierError, InvalidRecordError
from podcast_analyzer.validation import (
    FEATURE_LIMITS,
    check_range,
    parse_bool,
    parse_float,
    parse_int,
    parse_timestamp,
    validate_csv_filename,
    validate_recording_id,
    validate_speaker_id,
)


class SpeakerIdTests(unittest.TestCase):
    def test_valid_ids_are_accepted(self):
        for value in ("S001", "S999", "S000"):
            with self.subTest(value=value):
                self.assertEqual(validate_speaker_id(value), value)

    def test_invalid_ids_are_rejected(self):
        for value in ("001", "S01", "s001", "S0001", "", "S00a", "S001x", None, 1):
            with self.subTest(value=value):
                with self.assertRaises(InvalidIdentifierError):
                    validate_speaker_id(value)

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(validate_speaker_id("  S001 "), "S001")

    def test_message_names_the_expected_format(self):
        with self.assertRaises(InvalidIdentifierError) as context:
            validate_speaker_id("001")
        self.assertEqual(
            str(context.exception),
            "'001' is not a valid speaker ID (expected S followed by three digits, e.g. S001)",
        )
        self.assertEqual(context.exception.field, "speaker_id")
        self.assertEqual(context.exception.value, "001")

    def test_identifier_error_is_also_a_value_error(self):
        with self.assertRaises(ValueError):
            validate_speaker_id("nope")


class RecordingIdTests(unittest.TestCase):
    def test_valid_ids_are_accepted(self):
        for value in ("REC-2026-001", "REC-1999-999"):
            with self.subTest(value=value):
                self.assertEqual(validate_recording_id(value), value)

    def test_invalid_ids_are_rejected(self):
        for value in (
            "REC-26-102", "REC-2026-1", "REC-2026-0001", "rec-2026-001",
            " REC-2026-001x", "REC_2026_001", "2026-001", "", None,
        ):
            with self.subTest(value=value):
                with self.assertRaises(InvalidIdentifierError):
                    validate_recording_id(value)

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(validate_recording_id(" REC-2026-001\t"), "REC-2026-001")

    def test_message_names_the_expected_format(self):
        with self.assertRaises(InvalidIdentifierError) as context:
            validate_recording_id("REC-26-102")
        self.assertIn("'REC-26-102' is not a valid recording ID", str(context.exception))
        self.assertIn("REC-2026-001", str(context.exception))
        self.assertEqual(context.exception.field, "recording_id")


class CsvFilenameTests(unittest.TestCase):
    def test_csv_names_are_accepted(self):
        for name in (
            "speakers.csv", "recording_sessions-2.csv", "My Data.CSV", "a.b.csv",
            "recording_sessions (1).csv", "data+extra.csv", "data;v2.csv",
        ):
            with self.subTest(name=name):
                validate_csv_filename(Path("some") / "folder" / name)

    def test_other_names_are_rejected(self):
        for name in ("notes.txt", "speakers", "data.csv.bak", ".csv", "a<b.csv", 'say"hi".csv', "tab\t.csv"):
            with self.subTest(name=name):
                with self.assertRaises(DataFileError):
                    validate_csv_filename(Path("folder") / name)

    def test_error_carries_the_path(self):
        with self.assertRaises(DataFileError) as context:
            validate_csv_filename(Path("folder/notes.txt"))
        self.assertEqual(context.exception.path, Path("folder/notes.txt"))
        self.assertIn("not a CSV file name", context.exception.reason)


class ParseTests(unittest.TestCase):
    def test_parse_int(self):
        self.assertEqual(parse_int("timestamp", " 12 "), 12)
        self.assertIsInstance(parse_int("timestamp", "0"), int)

    def test_parse_int_messages(self):
        for text, message in (
            ("", "timestamp is missing"),
            ("   ", "timestamp is missing"),
            ("two", "timestamp must be a whole number, got 'two'"),
            ("1.5", "timestamp must be a whole number, got '1.5'"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as context:
                    parse_int("timestamp", text)
                self.assertEqual(str(context.exception), message)

    def test_parse_float(self):
        self.assertEqual(parse_float("pitch", " 148 "), 148.0)
        self.assertIsInstance(parse_float("pitch", "148"), float)

    def test_parse_float_messages(self):
        for text, message in (
            ("", "pitch is missing"),
            ("high", "pitch must be a number, got 'high'"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as context:
                    parse_float("pitch", text)
                self.assertEqual(str(context.exception), message)

    def test_nan_and_infinity_are_rejected(self):
        for text in ("nan", "NaN", "inf", "-inf", "Infinity"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as context:
                    parse_float("energy", text)
                self.assertIn("must be a finite number", str(context.exception))

    def test_parse_bool(self):
        for text, expected in (("True", True), ("False", False), (" True ", True), ("\tFalse", False)):
            with self.subTest(text=text):
                self.assertIs(parse_bool("speech_present", text), expected)

    def test_parse_bool_messages(self):
        # Only the exact spellings from the data dictionary are accepted.
        for text, message in (
            ("true", "speech_present must be True or False, got 'true'"),
            ("TRUE", "speech_present must be True or False, got 'TRUE'"),
            ("false", "speech_present must be True or False, got 'false'"),
            ("yes", "speech_present must be True or False, got 'yes'"),
            ("1", "speech_present must be True or False, got '1'"),
            ("", "speech_present is missing"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as context:
                    parse_bool("speech_present", text)
                self.assertEqual(str(context.exception), message)

    def test_parse_timestamp(self):
        self.assertEqual(parse_timestamp("0"), 0)
        self.assertEqual(parse_timestamp("7"), 7)
        with self.assertRaises(ValueError) as context:
            parse_timestamp("-1")
        self.assertEqual(str(context.exception), "timestamp must be 0 or more, got -1")
        with self.assertRaises(ValueError):
            parse_timestamp("abc")


class ExceptionClassTests(unittest.TestCase):
    def test_row_errors_are_value_errors(self):
        self.assertTrue(issubclass(InvalidIdentifierError, ValueError))
        self.assertTrue(issubclass(InvalidRecordError, ValueError))

    def test_file_error_is_not_a_value_error(self):
        # A whole-file problem must not be swallowed by a row-level "except ValueError".
        self.assertTrue(issubclass(DataFileError, Exception))
        self.assertFalse(issubclass(DataFileError, ValueError))

    def test_record_error_keeps_every_problem(self):
        error = InvalidRecordError([("pitch", "pitch is missing"), ("energy", "energy -0.2 is outside")])
        self.assertEqual(error.problems, [("pitch", "pitch is missing"), ("energy", "energy -0.2 is outside")])
        self.assertEqual(str(error), "pitch: pitch is missing; energy: energy -0.2 is outside")

    def test_record_error_needs_a_problem(self):
        with self.assertRaises(ValueError):
            InvalidRecordError([])

    def test_file_error_carries_path_and_reason(self):
        error = DataFileError(Path("data/x.csv"), "file not found")
        self.assertEqual((error.path, error.reason), (Path("data/x.csv"), "file not found"))
        self.assertEqual(str(error), "data/x.csv: file not found")


class RangeTests(unittest.TestCase):
    OUTSIDE = {
        "pitch": (44.9, 450.1),
        "energy": (-0.01, 1.01),
        "speech_rate": (29.9, 260.1),
        "pause_ratio": (-0.01, 1.01),
        "background_noise": (-0.01, 1.01),
        "signal_quality": (-0.01, 1.01),
    }

    def test_every_feature_has_limits_and_a_test(self):
        self.assertEqual(set(FEATURE_LIMITS), set(self.OUTSIDE))

    def test_exact_limits_are_accepted(self):
        for feature, (low, high) in FEATURE_LIMITS.items():
            for value in (low, high):
                with self.subTest(feature=feature, value=value):
                    self.assertEqual(check_range(feature, value), value)

    def test_values_just_outside_are_rejected(self):
        for feature, values in self.OUTSIDE.items():
            for value in values:
                with self.subTest(feature=feature, value=value):
                    with self.assertRaises(ValueError):
                        check_range(feature, value)

    def test_message_shows_value_and_range(self):
        with self.assertRaises(ValueError) as context:
            check_range("pitch", 910.0)
        self.assertEqual(str(context.exception), "pitch 910.0 is outside the valid range 45-450")

    def test_feature_argument_selects_the_limits(self):
        self.assertEqual(check_range("baseline_pitch", 148.0, "pitch"), 148.0)
        with self.assertRaises(ValueError) as context:
            check_range("baseline_energy", 1.5, "energy")
        self.assertIn("baseline_energy 1.5 is outside the valid range 0-1", str(context.exception))

    def test_non_numbers_are_rejected(self):
        for value in (None, "148", True, [1]):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    check_range("pitch", value)

    def test_nan_is_never_in_range(self):
        with self.assertRaises(ValueError):
            check_range("pitch", math.nan)


if __name__ == "__main__":
    unittest.main()
