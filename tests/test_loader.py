"""Unit tests for podcast_analyzer.loader.

Fixtures are written into temporary directories; the official files in data/
are only read, never changed.

Run from the repository root with:  python -m unittest discover -s tests -t . -v
"""

import tempfile
import unittest
from pathlib import Path

from podcast_analyzer.exceptions import DataFileError
from podcast_analyzer.loader import (
    SESSION_COLUMNS,
    SPEAKER_COLUMNS,
    WITHHELD_NAME,
    load_recordings,
    load_speakers,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

SPEAKER_HEADER = ",".join(SPEAKER_COLUMNS)
SESSION_HEADER = ",".join(SESSION_COLUMNS)
GOOD_SPEAKERS = [
    "S001,Test One,150,0.40,120,0.25",
    "S002,Test Two,118,0.36,108,0.25",
]


def session_row(recording="REC-2026-001", speaker="S001", timestamp="0", speech="True",
                pitch="150", energy="0.40", rate="120", pause="0.25", noise="0.10", quality="0.92"):
    return ",".join([recording, speaker, timestamp, speech, pitch, energy, rate, pause, noise, quality])


class TempFilesTestCase(unittest.TestCase):
    """Gives every test its own temporary directory and a CSV-writing helper."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def write_csv(self, name, header, rows):
        path = self.directory / name
        # write_bytes keeps "\n" as it is on every platform (write_text's newline
        # argument would need Python 3.10).
        path.write_bytes(("\n".join([header, *rows]) + "\n").encode("utf-8"))
        return path

    def speakers(self):
        path = self.write_csv("speakers.csv", SPEAKER_HEADER, GOOD_SPEAKERS)
        speakers, rejected = load_speakers(path)
        self.assertEqual(rejected, [])
        return speakers

    def load_sessions(self, rows, name="sessions.csv"):
        path = self.write_csv(name, SESSION_HEADER, rows)
        return load_recordings([path], self.speakers())


class LoadSpeakersTests(TempFilesTestCase):
    def test_valid_file_loads_with_float_baselines(self):
        speakers = self.speakers()
        self.assertEqual(sorted(speakers), ["S001", "S002"])
        self.assertEqual(speakers["S001"].profile.pitch, 150.0)
        self.assertIsInstance(speakers["S001"].profile.pitch, float)
        self.assertEqual(speakers["S002"].name, "Test Two")

    def test_each_bad_row_is_rejected_with_its_field(self):
        rows = [
            "S001,Ok,150,0.40,120,0.25",
            "001,Bad Id,150,0.40,120,0.25",
            "S003,,150,0.40,120,0.25",
            "S004,Text,high,0.40,120,0.25",
            "S005,Range,150,1.40,120,0.25",
            "S001,Duplicate,150,0.40,120,0.25",
            "S006,Short,150",
        ]
        path = self.write_csv("speakers.csv", SPEAKER_HEADER, rows)
        speakers, rejected = load_speakers(path)
        self.assertEqual(list(speakers), ["S001"])
        self.assertEqual([r.row_number for r in rejected], [3, 4, 5, 6, 7, 8])
        self.assertTrue(all(r.filename == "speakers.csv" for r in rejected))
        self.assertEqual(
            [[field for field, _ in r.problems] for r in rejected],
            [["speaker_id"], ["name"], ["baseline_pitch"], ["baseline_energy"], ["speaker_id"], ["(row)"]],
        )
        self.assertIn("first defined on row 2", rejected[4].problems[0][1])

    def test_rejected_rows_do_not_repeat_the_name(self):
        path = self.write_csv("speakers.csv", SPEAKER_HEADER, ["001,Secret Name,150,0.40,120,0.25"])
        _, rejected = load_speakers(path)
        self.assertNotIn("Secret Name", rejected[0].raw_values)
        self.assertIn(WITHHELD_NAME, rejected[0].raw_values)

    def test_missing_file_is_fatal(self):
        with self.assertRaises(DataFileError) as context:
            load_speakers(self.directory / "missing.csv")
        self.assertEqual(context.exception.reason, "file not found")

    def test_row_of_empty_fields_is_rejected(self):
        path = self.write_csv("speakers.csv", SPEAKER_HEADER, ["S001,Ok,150,0.40,120,0.25", ",,,,,", ""])
        speakers, rejected = load_speakers(path)
        self.assertEqual(list(speakers), ["S001"])
        self.assertEqual([r.row_number for r in rejected], [3])
        self.assertEqual(rejected[0].problems, (("(row)", "every field is empty"),))

    def test_bad_extension_is_fatal(self):
        path = self.directory / "speakers.txt"
        path.write_text(SPEAKER_HEADER + "\n", encoding="utf-8")
        with self.assertRaises(DataFileError) as context:
            load_speakers(path)
        self.assertIn("not a CSV file name", context.exception.reason)

    def test_empty_file_and_missing_columns_are_fatal(self):
        empty = self.directory / "empty.csv"
        empty.write_text("", encoding="utf-8")
        with self.assertRaises(DataFileError) as context:
            load_speakers(empty)
        self.assertEqual(context.exception.reason, "file is empty")

        path = self.write_csv("partial.csv", "speaker_id,name", ["S001,Name"])
        with self.assertRaises(DataFileError) as context:
            load_speakers(path)
        self.assertIn("missing required column(s): baseline_pitch", context.exception.reason)

    def test_non_utf8_file_is_fatal(self):
        path = self.directory / "latin.csv"
        path.write_bytes(SPEAKER_HEADER.encode("utf-8") + b"\nS001,Bj\xf8rn,150,0.4,120,0.25\n")
        with self.assertRaises(DataFileError) as context:
            load_speakers(path)
        self.assertEqual(context.exception.reason, "is not valid UTF-8 text")


class LoadRecordingsValidTests(TempFilesTestCase):
    def test_valid_file_loads_with_correct_types(self):
        result = self.load_sessions([
            session_row(timestamp="0"),
            session_row(timestamp="1", pitch="152.5"),
        ])
        self.assertEqual(result.accepted_rows, 2)
        self.assertEqual(result.rejected, [])
        self.assertEqual(result.file_problems, [])
        self.assertEqual(result.files_read, ["sessions.csv"])
        session = result.sessions["REC-2026-001"]
        self.assertEqual(session.speaker.speaker_id, "S001")
        window = session.windows[1]
        self.assertIsInstance(window.timestamp, int)
        self.assertIs(window.speech_present, True)
        self.assertEqual(window.value("pitch"), 152.5)
        self.assertIsInstance(window.value("pitch"), float)
        self.assertEqual(window.source.filename, "sessions.csv")
        self.assertEqual(window.source.row_number, 3)

    def test_rows_are_grouped_by_recording(self):
        result = self.load_sessions([
            session_row("REC-2026-001", "S001", "0"),
            session_row("REC-2026-002", "S002", "0"),
            session_row("REC-2026-001", "S001", "1"),
        ])
        self.assertEqual(sorted(result.sessions), ["REC-2026-001", "REC-2026-002"])
        self.assertEqual(len(result.sessions["REC-2026-001"]), 2)

    def test_whitespace_around_values_is_accepted(self):
        result = self.load_sessions([session_row(recording=" REC-2026-001 ", speaker=" S001", pitch=" 150 ")])
        self.assertEqual(result.accepted_rows, 1)

    def test_speech_present_must_be_exactly_true_or_false(self):
        result = self.load_sessions([
            session_row(timestamp="0", speech=" True "),
            session_row(timestamp="1", speech="true"),
            session_row(timestamp="2", speech="FALSE", pitch="", energy="", rate="", pause=""),
        ])
        self.assertEqual(result.accepted_rows, 1)
        self.assertEqual([r.row_number for r in result.rejected], [3, 4])
        self.assertEqual(
            result.rejected[0].problems,
            (("speech_present", "speech_present must be True or False, got 'true'"),),
        )

    def test_no_speech_row_without_values_is_accepted(self):
        result = self.load_sessions([session_row(speech="False", pitch="", energy="", rate="", pause="")])
        window = result.sessions["REC-2026-001"].windows[0]
        self.assertIs(window.speech_present, False)
        self.assertIsNone(window.value("pitch"))
        self.assertEqual(window.status, "no speech")

    def test_blank_lines_are_skipped_but_still_counted_in_row_numbers(self):
        path = self.directory / "sessions.csv"
        path.write_text(
            "\n".join([SESSION_HEADER, session_row(timestamp="0"), "", session_row(timestamp="x")]) + "\n",
            encoding="utf-8",
        )
        result = load_recordings([path], self.speakers())
        self.assertEqual(result.accepted_rows, 1)
        self.assertEqual([r.row_number for r in result.rejected], [4])
        self.assertEqual(result.rows_read, 2)


class LoadRecordingsRejectionTests(TempFilesTestCase):
    def assert_rejected(self, row, fields, row_number=2):
        result = self.load_sessions([row])
        self.assertEqual(result.accepted_rows, 0)
        self.assertEqual(len(result.rejected), 1)
        record = result.rejected[0]
        self.assertEqual(record.filename, "sessions.csv")
        self.assertEqual(record.row_number, row_number)
        self.assertEqual([field for field, _ in record.problems], fields)
        return record

    def test_each_kind_of_invalid_row(self):
        cases = (
            ("bad recording id", session_row(recording="REC-26-102"), ["recording_id"]),
            ("bad speaker id", session_row(speaker="001"), ["speaker_id"]),
            ("negative timestamp", session_row(timestamp="-1"), ["timestamp"]),
            ("text timestamp", session_row(timestamp="two"), ["timestamp"]),
            ("bad bool", session_row(speech="yes"), ["speech_present"]),
            ("text pitch", session_row(pitch="high"), ["pitch"]),
            ("pitch too low", session_row(pitch="44.9"), ["pitch"]),
            ("energy too high", session_row(energy="1.01"), ["energy"]),
            ("negative rate", session_row(rate="-30"), ["speech_rate"]),
            ("pause too high", session_row(pause="1.20"), ["pause_ratio"]),
            ("noise negative", session_row(noise="-0.10"), ["background_noise"]),
            ("quality too high", session_row(quality="1.30"), ["signal_quality"]),
            ("quality nan", session_row(quality="nan"), ["signal_quality"]),
            ("quality missing", session_row(quality=""), ["signal_quality"]),
            ("pitch missing", session_row(pitch=""), ["pitch"]),
        )
        for label, row, fields in cases:
            with self.subTest(label=label):
                self.assert_rejected(row, fields)

    def test_boundary_values_are_accepted(self):
        rows = [
            session_row(timestamp="0", pitch="45", energy="0", rate="30", pause="0", noise="0", quality="0"),
            session_row(timestamp="1", pitch="450", energy="1", rate="260", pause="1", noise="1", quality="1"),
        ]
        self.assertEqual(self.load_sessions(rows).accepted_rows, 2)

    def test_multiple_problems_in_one_row_are_all_reported(self):
        record = self.assert_rejected(
            session_row(timestamp="two", pitch="high", energy="-0.20", pause="1.20"),
            ["timestamp", "pitch", "energy", "pause_ratio"],
        )
        self.assertIn("timestamp must be a whole number, got 'two'", record.problems[0][1])
        self.assertIn("pitch must be a number, got 'high'", record.problems[1][1])

    def test_unknown_speaker_is_a_problem_not_a_crash(self):
        record = self.assert_rejected(session_row(speaker="S999"), ["speaker_id"])
        self.assertEqual(record.problems[0][1], "unknown speaker 'S999' (not in speakers.csv)")

    def test_unknown_speaker_message_uses_profiles_name(self):
        path = self.write_csv("sessions.csv", SESSION_HEADER, [session_row(speaker="S999")])
        result = load_recordings([path], self.speakers(), profiles_name="people.csv")
        self.assertIn("not in people.csv", result.rejected[0].problems[0][1])

    def test_no_speech_with_values_contradicts_itself(self):
        record = self.assert_rejected(session_row(speech="False"), ["speech_present"])
        self.assertIn("speech_present is False but pitch, energy, speech_rate, pause_ratio contain values",
                      record.problems[0][1])
        self.assertIn("contradicts itself", record.problems[0][1])

    def test_no_speech_with_one_value_uses_singular_wording(self):
        row = session_row(speech="False", pitch="150", energy="", rate="", pause="")
        record = self.assert_rejected(row, ["speech_present"])
        self.assertIn("pitch contains a value", record.problems[0][1])

    def test_rows_of_empty_fields_are_rejected_not_skipped(self):
        # Any length: an empty record is reported as empty, not as too short.
        for label, row in (("full width", ",,,,,,,,,"), ("short", ",,"), ("whitespace", " , ,\t,,,,,,,")):
            with self.subTest(label=label):
                record = self.assert_rejected(row, ["(row)"])
                self.assertEqual(record.problems[0][1], "every field is empty")
                self.assertIsNone(record.recording_id)

    def test_short_and_long_rows_are_rejected_by_length(self):
        short = ",".join(session_row().split(",")[:9])
        long = session_row() + ",extra"
        for label, row, found in (("short", short, 9), ("long", long, 11)):
            with self.subTest(label=label):
                record = self.assert_rejected(row, ["(row)"])
                self.assertEqual(record.problems[0][1], f"expected 10 values, found {found}")

    def test_speaker_clash_within_a_recording(self):
        result = self.load_sessions([
            session_row("REC-2026-001", "S001", "0"),
            session_row("REC-2026-001", "S002", "1"),
        ])
        self.assertEqual(result.accepted_rows, 1)
        self.assertEqual(len(result.sessions["REC-2026-001"]), 1)
        record = result.rejected[0]
        self.assertEqual(record.row_number, 3)
        self.assertEqual(record.problems, (("speaker_id", "REC-2026-001 already belongs to S001"),))

    def test_duplicate_timestamp_is_rejected(self):
        result = self.load_sessions([session_row(timestamp="3"), session_row(timestamp="3", pitch="160")])
        self.assertEqual(result.accepted_rows, 1)
        record = result.rejected[0]
        self.assertEqual(record.row_number, 3)
        self.assertEqual(record.problems[0][0], "timestamp")
        self.assertIn("duplicate timestamp 3 in REC-2026-001", record.problems[0][1])
        self.assertEqual(result.sessions["REC-2026-001"].windows[0].value("pitch"), 150.0)

    def test_rejected_rows_keep_raw_values_and_valid_recording_id(self):
        result = self.load_sessions([
            session_row(speaker="S999"),
            session_row(recording="REC-26-102", timestamp="1"),
        ])
        by_row = {record.row_number: record for record in result.rejected}
        self.assertEqual(by_row[2].raw_values, tuple(session_row(speaker="S999").split(",")))
        self.assertEqual(by_row[2].recording_id, "REC-2026-001")
        self.assertIsNone(by_row[3].recording_id)
        self.assertEqual(result.fully_rejected_recordings, ["REC-2026-001"])

    def test_rejections_are_sorted_by_file_then_row(self):
        speakers = self.speakers()
        b = self.write_csv("b.csv", SESSION_HEADER, [session_row(timestamp="x")])
        a = self.write_csv("a.csv", SESSION_HEADER, [session_row(timestamp="0"), session_row(timestamp="y")])
        result = load_recordings([b, a], speakers)
        self.assertEqual([(r.filename, r.row_number) for r in result.rejected], [("a.csv", 3), ("b.csv", 2)])
        self.assertEqual(result.files_read, ["b.csv", "a.csv"])
        self.assertEqual(result.rows_read, 3)


class LoadRecordingsFileProblemTests(TempFilesTestCase):
    def test_missing_session_file_is_reported_and_loading_continues(self):
        speakers = self.speakers()
        good = self.write_csv("good.csv", SESSION_HEADER, [session_row()])
        result = load_recordings([self.directory / "missing.csv", good], speakers)
        self.assertEqual(result.accepted_rows, 1)
        self.assertEqual(result.files_read, ["good.csv"])
        self.assertEqual(len(result.file_problems), 1)
        problem = result.file_problems[0]
        self.assertIsInstance(problem, DataFileError)
        self.assertEqual(problem.path.name, "missing.csv")
        self.assertEqual(problem.reason, "file not found")

    def test_only_missing_files_gives_no_files_read(self):
        result = load_recordings([self.directory / "missing.csv"], self.speakers())
        self.assertEqual(result.files_read, [])
        self.assertEqual(result.sessions, {})
        self.assertEqual(len(result.file_problems), 1)

    def test_empty_file(self):
        path = self.directory / "empty.csv"
        path.write_text("", encoding="utf-8")
        result = load_recordings([path], self.speakers())
        self.assertEqual(result.file_problems[0].reason, "file is empty")
        self.assertEqual(result.files_read, [])

    def test_missing_columns(self):
        path = self.write_csv("short.csv", "recording_id,speaker_id,timestamp", ["REC-2026-001,S001,0"])
        result = load_recordings([path], self.speakers())
        self.assertIn("missing required column(s): speech_present", result.file_problems[0].reason)
        self.assertEqual(result.accepted_rows, 0)

    def test_non_utf8_bytes(self):
        path = self.directory / "latin.csv"
        path.write_bytes(SESSION_HEADER.encode("utf-8") + b"\nREC-2026-001,S001,0,True,\xff\xfe,0,0,0,0,0\n")
        result = load_recordings([path], self.speakers())
        self.assertEqual(result.file_problems[0].reason, "is not valid UTF-8 text")
        self.assertEqual(result.accepted_rows, 0)

    def test_bad_file_extension(self):
        path = self.directory / "sessions.txt"
        path.write_text(SESSION_HEADER + "\n" + session_row() + "\n", encoding="utf-8")
        result = load_recordings([path], self.speakers())
        self.assertIn("not a CSV file name", result.file_problems[0].reason)
        self.assertEqual(result.files_read, [])

    def test_directory_instead_of_file(self):
        folder = self.directory / "folder.csv"
        folder.mkdir()
        result = load_recordings([folder], self.speakers())
        self.assertEqual(result.file_problems[0].reason, "is a directory, not a file")

    def test_same_file_listed_twice_is_read_once(self):
        path = self.write_csv("sessions.csv", SESSION_HEADER, [session_row()])
        result = load_recordings([path, path], self.speakers())
        self.assertEqual(result.accepted_rows, 1)
        self.assertEqual(result.rejected, [])
        self.assertEqual(len(result.file_problems), 1)
        self.assertIn("listed more than once", result.file_problems[0].reason)

    def test_header_with_byte_order_mark_and_extra_column(self):
        header = "﻿" + SESSION_HEADER + ",notes"
        path = self.directory / "bom.csv"
        path.write_bytes((header + "\n" + session_row() + ",hello\n").encode("utf-8"))
        result = load_recordings([path], self.speakers())
        self.assertEqual(result.accepted_rows, 1)


class ExtraFixtureTests(unittest.TestCase):
    """tests/fixtures/recording_sessions_extra.csv together with the official speakers.csv."""

    @classmethod
    def setUpClass(cls):
        speakers, _ = load_speakers(DATA_DIR / "speakers.csv")
        cls.result = load_recordings([FIXTURE_DIR / "recording_sessions_extra.csv"], speakers)

    def test_row_counts(self):
        self.assertEqual(self.result.accepted_rows, 11)
        self.assertEqual(self.result.rows_read, 13)
        self.assertEqual(self.result.file_problems, [])
        self.assertEqual(sorted(self.result.sessions), ["REC-2026-201", "REC-2026-202"])

    def test_lower_case_true_and_empty_row_are_rejected(self):
        by_row = {record.row_number: record for record in self.result.rejected}
        self.assertEqual(sorted(by_row), [8, 9])
        self.assertEqual(
            by_row[8].problems, (("speech_present", "speech_present must be True or False, got 'true'"),)
        )
        self.assertEqual(by_row[9].problems, (("(row)", "every field is empty"),))

    def test_recordings_are_linked_to_official_speakers(self):
        sessions = self.result.sessions
        self.assertEqual(sessions["REC-2026-201"].speaker.speaker_id, "S001")
        self.assertEqual(len(sessions["REC-2026-201"]), 6)
        self.assertEqual(sessions["REC-2026-202"].speaker.speaker_id, "S003")
        self.assertEqual(len(sessions["REC-2026-202"]), 5)
        self.assertEqual(len(sessions["REC-2026-202"].unreliable_windows), 3)


class OfficialDataTests(unittest.TestCase):
    def test_official_files_load_as_expected(self):
        speakers, speaker_rejections = load_speakers(DATA_DIR / "speakers.csv")
        self.assertEqual(sorted(speakers), ["S001", "S002", "S003"])
        self.assertEqual(speaker_rejections, [])

        result = load_recordings(
            [DATA_DIR / "recording_sessions.csv", DATA_DIR / "recording_sessions_invalid.csv"], speakers
        )
        self.assertEqual(result.accepted_rows, 26)
        self.assertEqual(len(result.rejected), 10)
        self.assertEqual(len(result.sessions), 6)
        self.assertEqual(result.file_problems, [])
        self.assertEqual(
            [r.row_number for r in result.rejected if r.filename == "recording_sessions_invalid.csv"],
            list(range(3, 13)),
        )
        self.assertEqual(
            [r.row_number for r in result.rejected if r.filename == "recording_sessions.csv"], []
        )
        self.assertEqual(result.fully_rejected_recordings, ["REC-2026-102", "REC-2026-103"])
        self.assertEqual(len(result.sessions["REC-2026-101"]), 1)


if __name__ == "__main__":
    unittest.main()
