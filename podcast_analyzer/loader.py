"""Read the CSV files and turn valid rows into domain objects.

This is where file and row problems are caught:

- a file that cannot be read at all raises DataFileError;
- a row that cannot be accepted is turned into a RejectedRecord and loading
  carries on with the next row.

Row numbers are CSV line numbers (csv.reader.line_num), so the header is row 1
and the first data row is row 2, which matches what a spreadsheet shows.
Only truly blank lines are skipped. A line of empty fields, such as ",,,,", is
a record with nothing in it, so it is rejected and reported like any other
bad row instead of disappearing silently.
"""

import csv
from pathlib import Path

from .exceptions import DataFileError, InvalidIdentifierError, InvalidRecordError
from .models import AcousticProfile, AcousticWindow, RecordingSession, SourceRow, Speaker
from .validation import (
    RECORDING_FEATURES,
    SPEECH_FEATURES,
    parse_bool,
    parse_feature,
    parse_timestamp,
    validate_csv_filename,
    validate_recording_id,
    validate_speaker_id,
)

SPEAKER_COLUMNS = (
    "speaker_id", "name", "baseline_pitch", "baseline_energy",
    "baseline_speech_rate", "baseline_pause_ratio",
)
SESSION_COLUMNS = (
    "recording_id", "speaker_id", "timestamp", "speech_present", "pitch", "energy",
    "speech_rate", "pause_ratio", "background_noise", "signal_quality",
)
# speakers.csv column -> the feature whose range it must respect.
BASELINE_FEATURES = {
    "baseline_pitch": "pitch",
    "baseline_energy": "energy",
    "baseline_speech_rate": "speech_rate",
    "baseline_pause_ratio": "pause_ratio",
}
# Rejected speaker rows are reported with this in place of the name, so the
# rejection report holds no more personal data than it needs.
WITHHELD_NAME = "[name withheld]"


class RejectedRecord:
    """A CSV row that was not accepted, with every reason and the raw values."""

    def __init__(self, filename, row_number, problems, raw_values, recording_id=None):
        self._filename = str(filename)
        self._row_number = int(row_number)
        self._problems = tuple((str(field), str(reason)) for field, reason in problems)
        self._raw_values = tuple(raw_values)
        self._recording_id = recording_id

    @property
    def filename(self):
        return self._filename

    @property
    def row_number(self):
        return self._row_number

    @property
    def problems(self):
        """(field, reason) pairs."""
        return self._problems

    @property
    def raw_values(self):
        return self._raw_values

    @property
    def recording_id(self):
        """The row's recording ID if it had a valid format, otherwise None."""
        return self._recording_id

    @property
    def sort_key(self):
        return (self._filename, self._row_number)

    def __repr__(self):
        return f"RejectedRecord({self._filename!r}, row {self._row_number}, {len(self._problems)} problem(s))"


class LoadResult:
    """Everything that came out of reading the recording-session files."""

    def __init__(self, sessions, rejected, file_problems, accepted_rows, files_read):
        self._sessions = dict(sessions)
        self._rejected = sorted(rejected, key=lambda record: record.sort_key)
        self._file_problems = list(file_problems)
        self._accepted_rows = accepted_rows
        self._files_read = list(files_read)

    @property
    def sessions(self):
        """recording_id -> RecordingSession."""
        return dict(self._sessions)

    @property
    def rejected(self):
        """RejectedRecord objects sorted by file name, then row number."""
        return list(self._rejected)

    @property
    def file_problems(self):
        """DataFileError objects for session files that could not be used."""
        return list(self._file_problems)

    @property
    def accepted_rows(self):
        return self._accepted_rows

    @property
    def rows_read(self):
        return self._accepted_rows + len(self._rejected)

    @property
    def files_read(self):
        """Names of the session files that were read, in the order given."""
        return list(self._files_read)

    @property
    def fully_rejected_recordings(self):
        """Valid recording IDs that appear only in rejected rows."""
        return sorted({
            record.recording_id for record in self._rejected
            if record.recording_id is not None and record.recording_id not in self._sessions
        })


# ---------------------------------------------------------------------------
# Reading a file
# ---------------------------------------------------------------------------

def read_csv(path, required_columns):
    """Read a whole CSV file and return (header, rows).

    rows is a list of (row_number, values). The file is read completely before
    any row is used, so a file that fails halfway adds nothing.
    Raises DataFileError for any problem with the file as a whole.
    """
    path = Path(path)
    validate_csv_filename(path)
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            # csv.reader yields [] for a blank line and nothing else.
            rows = [(reader.line_num, row) for row in reader if row]
    except FileNotFoundError as error:
        raise DataFileError(path, "file not found") from error
    except IsADirectoryError as error:
        raise DataFileError(path, "is a directory, not a file") from error
    except PermissionError as error:
        # Windows reports opening a directory as a permission problem.
        reason = "is a directory, not a file" if path.is_dir() else "permission denied"
        raise DataFileError(path, reason) from error
    except UnicodeDecodeError as error:
        raise DataFileError(path, "is not valid UTF-8 text") from error
    except csv.Error as error:
        raise DataFileError(path, f"is not a readable CSV file ({error})") from error

    if header is None:
        raise DataFileError(path, "file is empty")
    # Strip spaces and a byte-order mark that some spreadsheet programs add.
    header = [name.strip().lstrip("﻿").strip() for name in header]
    missing = [column for column in required_columns if column not in header]
    if missing:
        raise DataFileError(path, "missing required column(s): " + ", ".join(missing))
    return header, rows


def _row_values(header, raw):
    """Map column name -> value, or raise InvalidRecordError if the row is empty or has the wrong length."""
    # Checked before the length, because "every field is empty" says more
    # about ",,," than a count of missing values would.
    if not any(cell.strip() for cell in raw):
        raise InvalidRecordError([("(row)", "every field is empty")])
    if len(raw) != len(header):
        raise InvalidRecordError([("(row)", f"expected {len(header)} values, found {len(raw)}")])
    return dict(zip(header, raw))


def _parse_into(problems, field, parser, *args):
    """Run one parser; on a ValueError record the problem and return None.

    Collecting problems instead of stopping at the first one means a rejected
    row lists everything that is wrong with it.
    """
    try:
        return parser(*args)
    except ValueError as error:
        problems.append((field, str(error)))
        return None


# ---------------------------------------------------------------------------
# Speakers
# ---------------------------------------------------------------------------

def load_speakers(path):
    """Read speakers.csv and return (speakers by ID, rejected rows).

    A bad row is rejected and reported; a file that cannot be read raises
    DataFileError, because no recording can be analysed without profiles.
    """
    path = Path(path)
    header, rows = read_csv(path, SPEAKER_COLUMNS)
    speakers = {}
    first_rows = {}
    rejected = []
    for row_number, raw in rows:
        try:
            speaker = _parse_speaker(_row_values(header, raw), speakers, first_rows)
        except InvalidRecordError as error:
            rejected.append(
                RejectedRecord(path.name, row_number, error.problems, _withhold_name(header, raw))
            )
            continue
        speakers[speaker.speaker_id] = speaker
        first_rows[speaker.speaker_id] = row_number
    return speakers, rejected


def _parse_speaker(values, speakers, first_rows):
    problems = []
    speaker_id = _parse_into(problems, "speaker_id", validate_speaker_id, values["speaker_id"])
    if speaker_id in speakers:
        problems.append((
            "speaker_id", f"duplicate speaker ID {speaker_id} (first defined on row {first_rows[speaker_id]})"
        ))
    name = values["name"].strip()
    if not name:
        problems.append(("name", "name is missing"))
    baselines = {}
    for column, feature in BASELINE_FEATURES.items():
        baselines[feature] = _parse_into(problems, column, parse_feature, column, values[column], feature)
    if problems:
        raise InvalidRecordError(problems)
    return Speaker(speaker_id, name, AcousticProfile(**baselines))


def _withhold_name(header, raw):
    values = list(raw)
    index = header.index("name")
    if index < len(values) and values[index].strip():
        values[index] = WITHHELD_NAME
    return values


# ---------------------------------------------------------------------------
# Recording sessions
# ---------------------------------------------------------------------------

class RecordingLoader:
    """Reads one or more session files into RecordingSession objects.

    Rows are grouped by recording_id, and each recording is linked to a
    speaker from the profiles. A file that cannot be read is recorded as a
    file problem and the loader moves on to the next file.
    """

    def __init__(self, speakers, profiles_name="speakers.csv"):
        self._speakers = dict(speakers)
        self._profiles_name = profiles_name
        self._reset()

    def _reset(self):
        self._sessions = {}
        self._rejected = []
        self._file_problems = []
        self._accepted_rows = 0

    def load(self, paths):
        """Read every file in paths and return a LoadResult."""
        self._reset()
        files_read = []
        seen = set()
        for path in paths:
            path = Path(path)
            # The same file twice would turn every row into a duplicate timestamp.
            key = path.resolve()
            if key in seen:
                self._file_problems.append(DataFileError(path, "listed more than once; read only once"))
                continue
            seen.add(key)
            try:
                header, rows = read_csv(path, SESSION_COLUMNS)
            except DataFileError as error:
                self._file_problems.append(error)
                continue
            files_read.append(path.name)
            for row_number, raw in rows:
                self._load_row(header, raw, SourceRow(path.name, row_number))
        return LoadResult(
            self._sessions, self._rejected, self._file_problems, self._accepted_rows, files_read
        )

    def _load_row(self, header, raw, source):
        try:
            self._accept(_row_values(header, raw), source)
        except InvalidRecordError as error:
            self._rejected.append(RejectedRecord(
                source.filename, source.row_number, error.problems, raw, _valid_recording_id(header, raw)
            ))
        else:
            self._accepted_rows += 1

    def _accept(self, values, source):
        """Validate one row and add it to its recording, or raise InvalidRecordError."""
        problems = []
        recording_id = self._identifier(problems, "recording_id", validate_recording_id, values)
        speaker = self._speaker(problems, values)
        timestamp = _parse_into(problems, "timestamp", parse_timestamp, values["timestamp"])
        speech_present = _parse_into(
            problems, "speech_present", parse_bool, "speech_present", values["speech_present"]
        )

        # Speech features first, so problems are listed in column order.
        features = {}
        filled = [feature for feature in SPEECH_FEATURES if values[feature].strip()]
        if speech_present is False:
            if filled:
                verb = "contains a value" if len(filled) == 1 else "contain values"
                problems.append((
                    "speech_present",
                    f"speech_present is False but {', '.join(filled)} {verb}; the row contradicts itself",
                ))
            features.update({feature: None for feature in SPEECH_FEATURES})
        else:
            # With speech present every speech feature is required. When
            # speech_present itself is invalid we cannot tell whether they are
            # required, so only the values that are there are checked.
            checked = SPEECH_FEATURES if speech_present else filled
            for feature in checked:
                features[feature] = _parse_into(problems, feature, parse_feature, feature, values[feature])
        for feature in RECORDING_FEATURES:
            features[feature] = _parse_into(problems, feature, parse_feature, feature, values[feature])

        # The first accepted row of a recording decides its speaker.
        session = self._sessions.get(recording_id)
        owner = session.speaker.speaker_id if session is not None else None
        if speaker is not None and owner not in (None, speaker.speaker_id):
            problems.append((
                "speaker_id", f"{recording_id} already belongs to {owner}"
            ))
        if problems:
            raise InvalidRecordError(problems)

        window = AcousticWindow(timestamp, speech_present, features, source)
        if session is None:
            session = RecordingSession(recording_id, speaker)
        # Raises InvalidRecordError for a duplicate timestamp.
        session.add_window(window)
        self._sessions[recording_id] = session

    @staticmethod
    def _identifier(problems, field, validator, values):
        try:
            return validator(values[field])
        except InvalidIdentifierError as error:
            problems.append((field, str(error)))
            return None

    def _speaker(self, problems, values):
        speaker_id = self._identifier(problems, "speaker_id", validate_speaker_id, values)
        if speaker_id is None:
            return None
        try:
            return self._speakers[speaker_id]
        except KeyError:
            problems.append((
                "speaker_id", f"unknown speaker '{speaker_id}' (not in {self._profiles_name})"
            ))
            return None


def _valid_recording_id(header, raw):
    """Return the row's recording ID if it is there and well formed, so fully
    rejected recordings can still be named in the report."""
    index = header.index("recording_id")
    if index >= len(raw):
        return None
    try:
        return validate_recording_id(raw[index])
    except InvalidIdentifierError:
        return None


def load_recordings(paths, speakers, profiles_name="speakers.csv"):
    """Read the session files and return a LoadResult (see RecordingLoader)."""
    return RecordingLoader(speakers, profiles_name).load(paths)
