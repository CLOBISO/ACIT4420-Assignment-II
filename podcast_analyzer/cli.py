"""Command-line entry point: load, analyse, write the reports and print a summary.

Exit codes: 0 when the reports were written (rejected rows are expected and do
not count as failure); 1 when the speaker profiles cannot be read, no session
file can be read, or the reports cannot be written. Expected data problems
print a short "Error: ..." line, never a traceback.
"""

import argparse
import sys
from pathlib import Path

from .analysis import SessionAnalyzer
from .exceptions import DataFileError
from .loader import load_recordings, load_speakers
from .reporting import ReportWriter, build_overview, format_run_counts

DEFAULT_PROFILES = "data/speakers.csv"
DEFAULT_SESSIONS = ["data/recording_sessions.csv", "data/recording_sessions_invalid.csv"]
DEFAULT_OUTPUT = "output"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Analyse podcast recording sessions against each speaker's usual voice.",
    )
    # Relative defaults are resolved against the current directory, so run
    # the program from the repository root.
    parser.add_argument(
        "--profiles", default=DEFAULT_PROFILES,
        help=f"speaker profiles CSV (default: {DEFAULT_PROFILES})",
    )
    parser.add_argument(
        "--sessions", nargs="+", default=DEFAULT_SESSIONS,
        help="one or more recording session CSV files (default: " + " ".join(DEFAULT_SESSIONS) + ")",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help=f"directory for the report files, created if missing (default: {DEFAULT_OUTPUT})",
    )
    return parser


def format_summary(overview, written):
    """Return the console completion summary.

    The counts use the same lines as the report header (format_run_counts).
    """
    lines = ["Podcast Voice and Recording Analyzer", *format_run_counts(overview), "Reports written:"]
    lines.extend(f"  {path.as_posix()}" for path in written)
    return "\n".join(lines)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        speakers, speaker_rejections = load_speakers(args.profiles)
        load_result = load_recordings(args.sessions, speakers, profiles_name=Path(args.profiles).name)
        if not load_result.files_read:
            reasons = "; ".join(str(problem) for problem in load_result.file_problems)
            print(f"Error: no session file could be read ({reasons})", file=sys.stderr)
            return 1

        results = SessionAnalyzer().analyze_all(load_result.sessions)
        overview = build_overview(args.profiles, speakers, speaker_rejections, load_result, results)
        writer = ReportWriter(args.output)
        written = writer.write_all(
            results, overview, speaker_rejections, load_result.rejected, load_result.file_problems
        )
    except DataFileError as error:
        # The only place a whole-file problem stops the program.
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(format_summary(overview, written))
    return 0
