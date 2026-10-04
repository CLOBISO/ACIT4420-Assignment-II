"""The analyser's own exception classes.

Row-level problems (InvalidIdentifierError, InvalidRecordError) are caught by
the loader, which rejects the row and carries on. File-level problems
(DataFileError) stop the use of one file; the command line decides whether
the run can continue without it.
"""

from pathlib import Path


class InvalidIdentifierError(ValueError):
    """An identifier such as a speaker ID or recording ID has the wrong format.

    A ValueError, because it is a bad value; code that only cares about "bad
    value" can catch it without knowing about this package.
    """

    def __init__(self, field, value, message):
        super().__init__(message)
        self.field = field
        self.value = value


class InvalidRecordError(ValueError):
    """A CSV row cannot be accepted.

    problems holds every (field, reason) pair found in the row, not only the
    first, so the rejection report shows everything that needs fixing at once.
    """

    def __init__(self, problems):
        self.problems = [(str(field), str(reason)) for field, reason in problems]
        if not self.problems:
            raise ValueError("InvalidRecordError needs at least one problem")
        super().__init__("; ".join(f"{field}: {reason}" for field, reason in self.problems))


class DataFileError(Exception):
    """A whole file or directory cannot be used: missing, unreadable, not UTF-8, not CSV, ..."""

    def __init__(self, path, reason):
        self.path = Path(path)
        self.reason = str(reason)
        super().__init__(f"{self.path.as_posix()}: {self.reason}")
