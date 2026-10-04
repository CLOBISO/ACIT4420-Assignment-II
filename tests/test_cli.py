"""Tests for the command line entry point, podcast_analyzer.cli.main.

Every run writes into a temporary directory; nothing is written inside the
repository. Paths are absolute, so the tests work from any current directory.

Run from the repository root with:  python -m unittest discover -s tests -t . -v
"""

import contextlib
import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from podcast_analyzer import cli
from podcast_analyzer.reporting import SUMMARY_COLUMNS

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PROFILES = DATA_DIR / "speakers.csv"
VALID_SESSIONS = DATA_DIR / "recording_sessions.csv"
INVALID_SESSIONS = DATA_DIR / "recording_sessions_invalid.csv"
EXTRA_SESSIONS = Path(__file__).resolve().parent / "fixtures" / "recording_sessions_extra.csv"
# The run-level lines of the console summary; the report header repeats them.
EXPECTED_COUNTS = [
    "Speaker profiles:     speakers.csv (3 accepted, 0 rejected)",
    "Session files read:   recording_sessions.csv, recording_sessions_invalid.csv",
    "Files not processed:  none",
    "Session rows:         36 read, 26 accepted, 10 rejected",
    "Recordings:           6 (4 analysed, 2 insufficient data)",
]
OUTPUT_FILES = ("analysis_summary.csv", "analysis_report.txt", "rejected_records.txt")


class CliTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def run_cli(self, output, profiles=PROFILES, sessions=(VALID_SESSIONS, INVALID_SESSIONS)):
        """Run main() and return (exit code, stdout text, stderr text)."""
        argv = ["--profiles", str(profiles), "--sessions", *map(str, sessions), "--output", str(output)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()


class SuccessfulRunTests(CliTestCase):
    def test_exit_zero_and_three_files_created(self):
        output = self.directory / "out"
        code, stdout, stderr = self.run_cli(output)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        for name in OUTPUT_FILES:
            with self.subTest(name=name):
                self.assertTrue((output / name).is_file())
                self.assertIn(name, stdout)

    def test_console_summary(self):
        output = self.directory / "out"
        _, stdout, _ = self.run_cli(output)
        expected = [
            "Podcast Voice and Recording Analyzer",
            *EXPECTED_COUNTS,
            "Reports written:",
            *(f"  {(output / name).as_posix()}" for name in OUTPUT_FILES),
        ]
        self.assertEqual(stdout.splitlines(), expected)

    def test_report_header_uses_the_console_wording(self):
        output = self.directory / "out"
        self.run_cli(output)
        header = (output / "analysis_report.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(header[2:2 + len(EXPECTED_COUNTS)], EXPECTED_COUNTS)
        self.assertIn("Every row rejected:   REC-2026-102, REC-2026-103", header)

    def test_nested_output_directory_is_created(self):
        output = self.directory / "a" / "b" / "c"
        self.assertFalse(output.exists())
        code, _, _ = self.run_cli(output)
        self.assertEqual(code, 0)
        self.assertTrue((output / "analysis_summary.csv").is_file())

    def test_summary_has_expected_header_and_one_row_per_recording(self):
        output = self.directory / "out"
        self.run_cli(output)
        with open(output / "analysis_summary.csv", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], list(SUMMARY_COLUMNS))
        recording_ids = [row[0] for row in rows[1:]]
        self.assertEqual(recording_ids, [
            "REC-2026-001", "REC-2026-002", "REC-2026-003",
            "REC-2026-004", "REC-2026-005", "REC-2026-101",
        ])
        self.assertTrue(all(len(row) == len(SUMMARY_COLUMNS) for row in rows))

    def test_summary_holds_the_expected_labels(self):
        output = self.directory / "out"
        self.run_cli(output)
        with open(output / "analysis_summary.csv", encoding="utf-8", newline="") as handle:
            styles = {row["recording_id"]: row["style"] for row in csv.DictReader(handle)}
        self.assertEqual(styles["REC-2026-002"], "energetic")
        self.assertEqual(styles["REC-2026-005"], "insufficient data")

    def test_single_window_recording_has_an_empty_quality_score(self):
        output = self.directory / "out"
        self.run_cli(output)
        with open(output / "analysis_summary.csv", encoding="utf-8", newline="") as handle:
            rows = {row["recording_id"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["REC-2026-101"]["quality_band"], "insufficient data")
        self.assertEqual(rows["REC-2026-101"]["quality_score"], "")
        self.assertEqual((rows["REC-2026-005"]["quality_band"], rows["REC-2026-005"]["quality_score"]),
                         ("acceptable", "69.0"))
        report = (output / "analysis_report.txt").read_text(encoding="utf-8")
        self.assertIn("Recording quality: INSUFFICIENT DATA\n", report)

    def test_running_twice_gives_byte_identical_files(self):
        output = self.directory / "out"
        self.run_cli(output)
        first = {name: (output / name).read_bytes() for name in OUTPUT_FILES}
        self.run_cli(output)
        for name in OUTPUT_FILES:
            with self.subTest(name=name):
                self.assertEqual((output / name).read_bytes(), first[name])

    def test_rerun_overwrites_stale_content(self):
        output = self.directory / "out"
        self.run_cli(output)
        expected = (output / "analysis_report.txt").read_bytes()
        (output / "analysis_report.txt").write_text("stale", encoding="utf-8")
        self.run_cli(output)
        self.assertEqual((output / "analysis_report.txt").read_bytes(), expected)

    def test_reports_do_not_contain_speaker_names(self):
        output = self.directory / "out"
        self.run_cli(output)
        for name in OUTPUT_FILES:
            text = (output / name).read_text(encoding="utf-8")
            for speaker_name in ("Amina", "Jonas", "Maya"):
                with self.subTest(file=name, speaker=speaker_name):
                    self.assertNotIn(speaker_name, text)

    def test_rejections_are_listed_in_the_rejected_file(self):
        output = self.directory / "out"
        self.run_cli(output)
        text = (output / "rejected_records.txt").read_text(encoding="utf-8")
        self.assertIn("recording_sessions_invalid.csv, row 3", text)
        self.assertIn("recording_sessions_invalid.csv, row 12", text)

    def test_rejected_file_header_and_problem_lines(self):
        output = self.directory / "out"
        self.run_cli(output)
        lines = (output / "rejected_records.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[2], "Rows rejected: 10 (0 in speakers.csv, 10 in session files)")
        # The field name is shown once, as the label, not repeated in the reason.
        for line in (
            "  - speech_present: must be True or False, got 'yes'",
            "  - pitch: is missing",
            "  - energy: -0.2 is outside the valid range 0-1",
            "  - timestamp: must be a whole number, got 'two'",
            "  - speaker_id: unknown speaker 'S999' (not in speakers.csv)",
            "  - (row): expected 10 values, found 9",
        ):
            with self.subTest(line=line):
                self.assertIn(line, lines)
        self.assertFalse(any(line.startswith("  - pitch: pitch ") for line in lines))

    def test_rejected_speaker_rows_are_counted_separately(self):
        profiles = self.directory / "people.csv"
        profiles.write_bytes(
            (PROFILES.read_text(encoding="utf-8") + "S004,,150,0.40,120,0.25\n").encode("utf-8")
        )
        output = self.directory / "out"
        code, stdout, _ = self.run_cli(output, profiles=profiles)
        self.assertEqual(code, 0)
        self.assertIn("Speaker profiles:     people.csv (3 accepted, 1 rejected)", stdout)
        lines = (output / "rejected_records.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[2], "Rows rejected: 11 (1 in people.csv, 10 in session files)")
        self.assertIn("  - name: is missing", lines)


class OtherSessionFileTests(CliTestCase):
    def test_one_session_file_as_in_the_assignment_example(self):
        # The shape of the command in the assignment text: only the valid file.
        output = self.directory / "out"
        code, stdout, stderr = self.run_cli(output, sessions=(VALID_SESSIONS,))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Session rows:         25 read, 25 accepted, 0 rejected", stdout)
        self.assertIn("Recordings:           5 (4 analysed, 1 insufficient data)", stdout)
        rejected = (output / "rejected_records.txt").read_text(encoding="utf-8")
        self.assertIn("Rows rejected: 0 (0 in speakers.csv, 0 in session files)", rejected)

    def test_official_files_plus_extra_fixture(self):
        output = self.directory / "out"
        code, stdout, stderr = self.run_cli(output, sessions=(VALID_SESSIONS, INVALID_SESSIONS, EXTRA_SESSIONS))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn(
            "Session files read:   recording_sessions.csv, recording_sessions_invalid.csv, "
            "recording_sessions_extra.csv",
            stdout,
        )
        self.assertIn("Session rows:         49 read, 37 accepted, 12 rejected", stdout)
        self.assertIn("Recordings:           8 (5 analysed, 3 insufficient data)", stdout)
        with open(output / "analysis_summary.csv", encoding="utf-8", newline="") as handle:
            rows = {row["recording_id"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["REC-2026-201"]["style"], "temporarily varied")
        self.assertEqual(rows["REC-2026-202"]["unreliable_windows"], "3")
        self.assertEqual(rows["REC-2026-202"]["style"], "insufficient data")
        rejected = (output / "rejected_records.txt").read_text(encoding="utf-8")
        self.assertIn("recording_sessions_extra.csv, row 8\n  - speech_present: must be True or False, got 'true'",
                      rejected)
        self.assertIn("recording_sessions_extra.csv, row 9\n  - (row): every field is empty", rejected)

    def test_downloaded_copy_name_is_accepted(self):
        # Browsers save a second download as "name (1).csv".
        copy = self.directory / "recording_sessions (1).csv"
        shutil.copyfile(VALID_SESSIONS, copy)
        output = self.directory / "out"
        code, stdout, stderr = self.run_cli(output, sessions=(copy,))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Session files read:   recording_sessions (1).csv", stdout)
        self.assertIn("Session rows:         25 read, 25 accepted, 0 rejected", stdout)


class ErrorRunTests(CliTestCase):
    def test_missing_profiles_file_exits_one(self):
        output = self.directory / "out"
        code, stdout, stderr = self.run_cli(output, profiles=self.directory / "missing.csv")
        self.assertEqual(code, 1)
        self.assertIn("Error", stderr)
        self.assertIn("file not found", stderr)
        self.assertEqual(stdout, "")
        self.assertFalse(output.exists())

    def test_one_missing_session_file_is_reported_but_run_succeeds(self):
        output = self.directory / "out"
        missing = self.directory / "gone.csv"
        code, stdout, stderr = self.run_cli(output, sessions=(VALID_SESSIONS, missing))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Files not processed:  ", stdout)
        self.assertIn("gone.csv", stdout)
        self.assertNotIn("Files not processed:  none", stdout)
        rejected = (output / "rejected_records.txt").read_text(encoding="utf-8")
        self.assertIn("gone.csv", rejected)
        self.assertTrue((output / "analysis_summary.csv").is_file())

    def test_no_readable_session_file_exits_one(self):
        code, _, stderr = self.run_cli(self.directory / "out", sessions=(self.directory / "gone.csv",))
        self.assertEqual(code, 1)
        self.assertIn("Error: no session file could be read", stderr)

    def test_output_path_that_is_a_file_exits_one(self):
        blocker = self.directory / "not_a_directory"
        blocker.write_text("occupied", encoding="utf-8")
        code, stdout, stderr = self.run_cli(blocker)
        self.assertEqual(code, 1)
        self.assertIn("Error", stderr)
        self.assertEqual(stdout, "")
        self.assertEqual(blocker.read_text(encoding="utf-8"), "occupied")

    def test_output_report_path_that_is_a_directory_exits_one(self):
        output = self.directory / "out"
        (output / "analysis_report.txt").mkdir(parents=True)
        code, _, stderr = self.run_cli(output)
        self.assertEqual(code, 1)
        self.assertIn("Error", stderr)
        self.assertIn("is a directory", stderr)


if __name__ == "__main__":
    unittest.main()
