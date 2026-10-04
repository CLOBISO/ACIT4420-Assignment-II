"""Validation rules and type conversion for single values.

Everything here is a pure function or a constant: no file access and no
knowledge of CSV rows. The loader combines these checks per row, and the model
classes reuse them to protect their own state.

Formats (identifiers, file names) are checked with regular expressions.
Numeric ranges are checked by converting first and comparing numbers, never
with a regular expression.
"""

import math
import re

from .exceptions import DataFileError, InvalidIdentifierError

SPEAKER_ID_PATTERN = re.compile(r"S\d{3}")
RECORDING_ID_PATTERN = re.compile(r"REC-\d{4}-\d{3}")
# Any ordinary file name ending in .csv: at least one character before the
# extension, and none of the characters Windows forbids in file names (which
# also covers '/' and control characters), so names such as
# "recording_sessions (1).csv" from a browser download still work.
CSV_FILENAME_PATTERN = re.compile(r'[^<>:"/\\|?*\x00-\x1f]+\.csv', re.IGNORECASE)

SPEECH_FEATURES = ("pitch", "energy", "speech_rate", "pause_ratio")
RECORDING_FEATURES = ("background_noise", "signal_quality")
ALL_FEATURES = SPEECH_FEATURES + RECORDING_FEATURES

# Valid ranges (inclusive), the same as in Assignment I's DATA_DESCRIPTION.md.
# The speaker baselines use the same ranges as the recorded features.
FEATURE_LIMITS = {
    "pitch": (45, 450),
    "energy": (0, 1),
    "speech_rate": (30, 260),
    "pause_ratio": (0, 1),
    "background_noise": (0, 1),
    "signal_quality": (0, 1),
}

# Signal-quality rules for accepted windows:
# - quality below 0.35: the measurement is too unreliable to describe the
#   voice, so the window is kept (the row itself is valid) but left out of the
#   speech analysis;
# - quality below 0.60 or noise above 0.60: the window is used but flagged.
UNRELIABLE_QUALITY_BELOW = 0.35
LOW_QUALITY_BELOW = 0.60
HIGH_NOISE_ABOVE = 0.60


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------

def _validate_identifier(field, label, value, pattern, expected):
    text = value.strip() if isinstance(value, str) else ""
    if not pattern.fullmatch(text):
        raise InvalidIdentifierError(field, value, f"{value!r} is not a valid {label} (expected {expected})")
    return text


def validate_speaker_id(value):
    """Return the stripped speaker ID, or raise InvalidIdentifierError."""
    return _validate_identifier(
        "speaker_id", "speaker ID", value, SPEAKER_ID_PATTERN,
        "S followed by three digits, e.g. S001",
    )


def validate_recording_id(value):
    """Return the stripped recording ID, or raise InvalidIdentifierError."""
    return _validate_identifier(
        "recording_id", "recording ID", value, RECORDING_ID_PATTERN,
        "REC-, a four-digit year, a hyphen and three digits, e.g. REC-2026-001",
    )


def validate_csv_filename(path):
    """Raise DataFileError unless the file name is an ordinary name ending in .csv."""
    if not CSV_FILENAME_PATTERN.fullmatch(path.name):
        raise DataFileError(path, "not a CSV file name (expected a file name ending in .csv)")


# ---------------------------------------------------------------------------
# Type conversion
# ---------------------------------------------------------------------------

def is_number(value):
    """Return True for int or float values. bool is rejected even though it subclasses int."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _required_text(field, text):
    stripped = text.strip() if isinstance(text, str) else ""
    if not stripped:
        raise ValueError(f"{field} is missing")
    return stripped


def parse_int(field, text):
    """Convert text to an int, with an error message that names the field."""
    stripped = _required_text(field, text)
    try:
        return int(stripped)
    except ValueError as error:
        raise ValueError(f"{field} must be a whole number, got {stripped!r}") from error


def parse_float(field, text):
    """Convert text to a finite float, with an error message that names the field."""
    stripped = _required_text(field, text)
    try:
        value = float(stripped)
    except ValueError as error:
        raise ValueError(f"{field} must be a number, got {stripped!r}") from error
    # float() happily accepts 'nan' and 'inf', which would poison every mean.
    if not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number, got {stripped!r}")
    return value


def parse_bool(field, text):
    """Convert exactly 'True' or 'False' to a bool.

    The data dictionary allows only these two spellings, so 'true', 'yes' or
    '1' are rejected instead of guessed at.
    """
    stripped = _required_text(field, text)
    if stripped == "True":
        return True
    if stripped == "False":
        return False
    raise ValueError(f"{field} must be True or False, got {stripped!r}")


def parse_timestamp(text):
    """Convert a timestamp to an int of 0 or more."""
    timestamp = parse_int("timestamp", text)
    if timestamp < 0:
        raise ValueError(f"timestamp must be 0 or more, got {timestamp}")
    return timestamp


# ---------------------------------------------------------------------------
# Ranges
# ---------------------------------------------------------------------------

def check_range(field, value, feature=None):
    """Return value if it lies within the feature's limits, otherwise raise ValueError.

    feature selects the limits when the field name differs from the feature
    name, e.g. check_range("baseline_pitch", 148.0, "pitch").
    """
    low, high = FEATURE_LIMITS[feature or field]
    if not is_number(value):
        raise ValueError(f"{field} must be a number, got {value!r}")
    if not low <= value <= high:
        raise ValueError(f"{field} {value} is outside the valid range {low}-{high}")
    return value


def parse_feature(field, text, feature=None):
    """Convert text to a float and check it against the feature's range."""
    return check_range(field, parse_float(field, text), feature)
