"""Turn analysis results into the three report files.

The format_* functions build text without touching the disk, so they can be
tested on their own. ReportWriter does the writing. Output holds no timestamps
and is always sorted, so running the program twice gives identical files.
Speakers are identified by ID only; names are never written.
"""

import csv
import io
from pathlib import Path

from .analysis import STATUS_INSUFFICIENT, round_for_display
from .exceptions import DataFileError

SUMMARY_FILENAME = "analysis_summary.csv"
REPORT_FILENAME = "analysis_report.txt"
REJECTED_FILENAME = "rejected_records.txt"

SUMMARY_COLUMNS = (
    "recording_id", "speaker_id", "source_files", "total_windows", "usable_windows",
    "no_speech_windows", "unreliable_windows", "flagged_windows", "status", "style",
    "quality_band", "quality_score", "mean_pitch", "pitch_change_pct", "mean_energy",
    "energy_change", "mean_speech_rate", "speech_rate_change_pct", "mean_pause_ratio",
    "pause_ratio_change", "mean_background_noise", "mean_signal_quality",
)

FEATURE_LABELS = {
    "pitch": "Pitch (Hz)",
    "energy": "Energy",
    "speech_rate": "Speech rate (wpm)",
    "pause_ratio": "Pause ratio",
    "background_noise": "Background noise",
    "signal_quality": "Signal quality",
}
DECIMALS = {
    "pitch": 1,
    "energy": 2,
    "speech_rate": 1,
    "pause_ratio": 2,
    "background_noise": 2,
    "signal_quality": 2,
}
# Change is shown as a percentage for these features and as a difference for
# the 0-1 ratios, matching the units the style rules use.
PERCENT_CHANGE = ("pitch", "speech_rate")
WIDTH = 74


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

def format_number(value, decimals):
    return "-" if value is None else f"{value:.{decimals}f}"


def format_csv_number(value, decimals):
    """Fixed decimals for the CSV, or an empty cell when there is no value."""
    return "" if value is None else f"{round_for_display(value, decimals):.{decimals}f}"


def format_change(feature, comparison):
    entry = comparison.get(feature)
    if not entry or entry["difference"] is None:
        return ""
    if feature in PERCENT_CHANGE and entry["percent"] is not None:
        return f"{round_for_display(entry['percent'], 1):+.1f}%"
    return f"{round_for_display(entry['difference'], 2):+.2f}"


def format_raw_values(values):
    """Write the raw values back as one CSV line, so quoting stays correct."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="").writerow(values)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# analysis_summary.csv
# ---------------------------------------------------------------------------

def summary_row(result):
    """Return one analysis_summary.csv row (a list of strings) for one result."""
    counts = result["windows"]
    summary = result["summary"]
    comparison = result["comparison"]

    def mean(feature):
        stats = summary.get(feature)
        return format_csv_number(stats["mean"] if stats else None, DECIMALS[feature])

    def change(feature, key):
        entry = comparison.get(feature) or {}
        decimals = 1 if key == "percent" else 2
        return format_csv_number(entry.get(key), decimals)

    score = result["quality"].get("score")
    return [
        result["recording_id"],
        result["speaker_id"],
        ";".join(result["source_files"]),
        str(counts["total"]),
        str(counts["usable"]),
        str(counts["no_speech"]),
        str(counts["unreliable"]),
        str(counts["flagged"]),
        result["status"],
        result["style"]["label"],
        result["quality"]["label"],
        format_csv_number(score, 1),
        mean("pitch"),
        change("pitch", "percent"),
        mean("energy"),
        change("energy", "difference"),
        mean("speech_rate"),
        change("speech_rate", "percent"),
        mean("pause_ratio"),
        change("pause_ratio", "difference"),
        mean("background_noise"),
        mean("signal_quality"),
    ]


# ---------------------------------------------------------------------------
# analysis_report.txt
# ---------------------------------------------------------------------------

def build_overview(profiles_path, speakers, speaker_rejections, load_result, results):
    """Collect the run-level numbers that the report header and the console summary share.

    Returns a dictionary with: profiles_file, speakers_loaded, speaker_rows_rejected,
    session_files, file_problems (list of "path: reason" strings), rows_read,
    rows_accepted, rows_rejected, recordings, recordings_analysed,
    recordings_insufficient and fully_rejected_recordings.
    """
    insufficient = sum(1 for result in results if result["status"] == STATUS_INSUFFICIENT)
    return {
        "profiles_file": Path(profiles_path).name,
        "speakers_loaded": len(speakers),
        "speaker_rows_rejected": len(speaker_rejections),
        "session_files": load_result.files_read,
        "file_problems": [str(problem) for problem in load_result.file_problems],
        "rows_read": load_result.rows_read,
        "rows_accepted": load_result.accepted_rows,
        "rows_rejected": len(load_result.rejected),
        "recordings": len(results),
        "recordings_analysed": len(results) - insufficient,
        "recordings_insufficient": insufficient,
        "fully_rejected_recordings": load_result.fully_rejected_recordings,
    }


def format_run_counts(overview):
    """Return the run-level lines shared by the report header and the console summary.

    Both places use this one function, so they always describe a run in the
    same words.
    """
    problems = overview["file_problems"]
    lines = [
        (
            f"Speaker profiles:     {overview['profiles_file']} ({overview['speakers_loaded']} accepted, "
            f"{overview['speaker_rows_rejected']} rejected)"
        ),
        "Session files read:   " + (", ".join(overview["session_files"]) or "none"),
        "Files not processed:  " + ("none" if not problems else problems[0]),
    ]
    lines.extend(f"{'':22}{problem}" for problem in problems[1:])
    lines += [
        (
            f"Session rows:         {overview['rows_read']} read, {overview['rows_accepted']} accepted, "
            f"{overview['rows_rejected']} rejected"
        ),
        (
            f"Recordings:           {overview['recordings']} ({overview['recordings_analysed']} analysed, "
            f"{overview['recordings_insufficient']} insufficient data)"
        ),
    ]
    return lines


def format_overview(overview):
    """Return the header block of analysis_report.txt."""
    lines = [
        "Podcast Voice and Recording Analyzer - analysis report",
        "=" * WIDTH,
        *format_run_counts(overview),
        "Every row rejected:   " + (", ".join(overview["fully_rejected_recordings"]) or "none"),
        f"Rejected rows:        listed in {REJECTED_FILENAME}",
    ]
    return "\n".join(lines)


def format_feature_table(summary, comparison):
    """Return one table row per feature: summary statistics plus the change from usual."""
    header = f"{'Feature':<19}{'Mean':>8}{'Min':>8}{'Max':>8}{'Stdev':>8}{'Usual':>8}{'Change':>9}"
    lines = [header, "-" * len(header)]
    for feature, label in FEATURE_LABELS.items():
        decimals = DECIMALS[feature]
        stats = summary.get(feature)
        entry = comparison.get(feature)
        usual = format_number(entry["usual"], decimals) if entry else ""
        if stats is None:
            lines.append(f"{label:<19}{'no usable values':>32}{usual:>8}")
            continue
        cells = "".join(
            f"{format_number(stats[key], decimals):>8}" for key in ("mean", "min", "max", "stdev")
        )
        lines.append(f"{label:<19}{cells}{usual:>8}{format_change(feature, comparison):>9}")
    # Noise and quality have no usual value, which would leave trailing spaces.
    return "\n".join(line.rstrip() for line in lines)


def format_window_notes(result):
    """List the excluded and flagged windows with their reasons."""
    lines = []
    if result["excluded"]:
        lines.append("Excluded windows (not used for the speech features)")
        for entry in result["excluded"]:
            lines.append(f"  t={entry['timestamp']!s:<4} {entry['reason']}")
    if result["warnings"]:
        lines.append("Flagged windows (still used)")
        for entry in result["warnings"]:
            lines.append(f"  t={entry['timestamp']!s:<4} " + "; ".join(entry["warnings"]))
    return "\n".join(lines)


def format_assessment(heading, assessment):
    label = assessment["label"].upper()
    if assessment.get("score") is not None:
        label += f" ({assessment['score']}/100)"
    lines = [f"{heading}: {label}"]
    lines.extend(f"  - {reason}" for reason in assessment["reasons"])
    return "\n".join(lines)


def format_recording(result):
    """Return the report block for one recording."""
    counts = result["windows"]
    parts = [
        "=" * WIDTH,
        f"{result['recording_id']}  |  speaker {result['speaker_id']}  |  {result['status']}",
        "Source: " + ", ".join(result["source_files"]),
        "-" * WIDTH,
        (
            f"Windows: {counts['total']} total, {counts['usable']} usable, "
            f"{counts['no_speech']} no speech, {counts['unreliable']} unreliable, "
            f"{counts['flagged']} flagged"
        ),
        "",
        format_feature_table(result["summary"], result["comparison"]),
    ]
    notes = format_window_notes(result)
    if notes:
        parts += ["", notes]
    parts += [
        "",
        format_assessment("Speaking style", result["style"]),
        format_assessment("Recording quality", result["quality"]),
    ]
    return "\n".join(parts)


def format_report(results, overview):
    """Return the complete analysis_report.txt content."""
    blocks = [format_overview(overview)]
    if results:
        blocks.extend(format_recording(result) for result in results)
    else:
        blocks.append("No recording had an accepted row, so nothing was analysed.")
    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# rejected_records.txt
# ---------------------------------------------------------------------------

def format_problem(field, reason):
    """Return one '  - field: reason' line without saying the field name twice.

    Most reasons are full sentences that start with the field name
    ("pitch is missing"); after the "pitch:" label that would read
    "pitch: pitch is missing", so the repeated name is dropped.
    """
    prefix = f"{field} "
    if reason.startswith(prefix):
        reason = reason[len(prefix):]
    return f"  - {field}: {reason}"


def format_rejections(speaker_rejections, session_rejections, file_problems, profiles_name):
    """Return the complete rejected_records.txt content.

    speaker_rejections and session_rejections hold RejectedRecord objects;
    together they are sorted by file name, then row number. profiles_name is
    the speaker profiles file name used in the header count.
    """
    records = sorted(
        list(speaker_rejections) + list(session_rejections), key=lambda record: record.sort_key
    )
    lines = [
        "Rejected records",
        "=" * WIDTH,
        (
            f"Rows rejected: {len(records)} ({len(speaker_rejections)} in {profiles_name}, "
            f"{len(session_rejections)} in session files)"
        ),
        "Row numbers are CSV line numbers: the header is row 1, the first data row is row 2.",
        "",
        "Files not processed:",
    ]
    lines.extend(f"  - {problem}" for problem in file_problems)
    if not file_problems:
        lines.append("  none")
    for record in records:
        lines += ["", f"{record.filename}, row {record.row_number}"]
        lines.extend(format_problem(field, reason) for field, reason in record.problems)
        lines.append(f"  raw: {format_raw_values(record.raw_values)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

class ReportWriter:
    """Writes the report files into one output directory, creating it if needed."""

    def __init__(self, output_dir):
        self._output_dir = Path(output_dir)
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except (FileExistsError, NotADirectoryError) as error:
            raise DataFileError(self._output_dir, "exists but is not a directory") from error
        except PermissionError as error:
            raise DataFileError(self._output_dir, "permission denied when creating the directory") from error
        except OSError as error:
            # Remaining file-system failures (disk full, invalid path, ...): the
            # operating system's own description is the most useful context.
            reason = f"cannot create the directory ({error.strerror})"
            raise DataFileError(self._output_dir, reason) from error

    @property
    def output_dir(self):
        return self._output_dir

    @property
    def summary_path(self):
        return self._output_dir / SUMMARY_FILENAME

    @property
    def report_path(self):
        return self._output_dir / REPORT_FILENAME

    @property
    def rejected_path(self):
        return self._output_dir / REJECTED_FILENAME

    def write_summary(self, results):
        """Write analysis_summary.csv, one row per recording sorted by recording_id."""
        rows = [summary_row(result) for result in sorted(results, key=lambda r: r["recording_id"])]

        def write(handle):
            writer = csv.writer(handle)
            writer.writerow(SUMMARY_COLUMNS)
            writer.writerows(rows)

        self._write(self.summary_path, write)
        return self.summary_path

    def write_report(self, results, overview):
        text = format_report(sorted(results, key=lambda r: r["recording_id"]), overview)
        self._write(self.report_path, lambda handle: handle.write(text))
        return self.report_path

    def write_rejections(self, speaker_rejections, session_rejections, file_problems, profiles_name):
        text = format_rejections(speaker_rejections, session_rejections, file_problems, profiles_name)
        self._write(self.rejected_path, lambda handle: handle.write(text))
        return self.rejected_path

    def write_all(self, results, overview, speaker_rejections, session_rejections, file_problems):
        """Write all three files and return their paths."""
        return [
            self.write_summary(results),
            self.write_report(results, overview),
            self.write_rejections(
                speaker_rejections, session_rejections, file_problems, overview["profiles_file"]
            ),
        ]

    @staticmethod
    def _write(path, write_content):
        # newline="" writes "\n" as it is, so the files are byte-identical on
        # every operating system; the csv module adds its own "\r\n".
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                write_content(handle)
        except IsADirectoryError as error:
            raise DataFileError(path, "is a directory, not a file") from error
        except PermissionError as error:
            # Windows reports writing to a directory as a permission problem.
            if path.is_dir():
                raise DataFileError(path, "is a directory, not a file") from error
            raise DataFileError(path, "permission denied (is the file open in another program?)") from error
        except OSError as error:
            raise DataFileError(path, f"cannot be written ({error.strerror})") from error
