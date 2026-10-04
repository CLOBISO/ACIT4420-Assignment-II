# Podcast Voice and Recording Analyzer

**ACIT4420 Programming Assignment II, Option B**

- **Student name:** Charlyn Joy Lacbayo Obiso
- **Student number:** 410318

## Description

Assignment I analysed generated windows held in Python lists and dictionaries. This version is a file-based application. It reads the speaker profiles and the recording-session windows from CSV files, validates every row, and carries on when a row or a file is bad. It groups the accepted rows by recording ID, links each recording to its speaker, and reuses the Assignment I analysis (summary, comparison with the speaker's usual voice, speaking style, recording quality). It then writes three report files and prints a short completion summary.

The program works on extracted numerical features only. It never sees audio or speech content. The three CSV files are the official ones and are not changed.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Entry point. Calls `podcast_analyzer.cli.main()` and passes its return value to `sys.exit`. |
| `podcast_analyzer/__init__.py` | Package docstring and `__all__`. |
| `podcast_analyzer/exceptions.py` | The three custom exceptions: `InvalidIdentifierError`, `InvalidRecordError`, `DataFileError`. |
| `podcast_analyzer/validation.py` | Regular expressions for formats, `parse_int`/`parse_float`/`parse_bool`/`parse_timestamp`, `FEATURE_LIMITS`, `check_range`, and the signal-quality constants. No file access. |
| `podcast_analyzer/models.py` | Domain classes: `AcousticProfile`, `Speaker`, `SourceRow`, `AcousticWindow`, `RecordingSession`. |
| `podcast_analyzer/loader.py` | Reads the CSV files (`read_csv`, `load_speakers`, `load_recordings`, `RecordingLoader`), turns valid rows into objects and bad rows into `RejectedRecord` objects. Result holder: `LoadResult`. |
| `podcast_analyzer/analysis.py` | Calculations, `Assessment`, `StyleAssessment`, `QualityAssessment` and `SessionAnalyzer`. Builds the result dictionary. |
| `podcast_analyzer/reporting.py` | Formats the report text and writes the three output files (`ReportWriter`). |
| `podcast_analyzer/cli.py` | Command-line options, the run sequence, the console summary and exit codes. |
| `data/speakers.csv`, `data/recording_sessions.csv`, `data/recording_sessions_invalid.csv` | The three official input files, unchanged. |
| `DATA_DICTIONARY.txt` | Describes the columns in the three files. |
| `tests/` | Unit tests (standard-library `unittest`) and `tests/fixtures/recording_sessions_extra.csv`, an extra input file for the tests. |
| `requirements.txt` | States that only the standard library is used. |
| `output/` | Created by the program. Holds the three report files. |

Dependencies go one way. `exceptions.py` imports nothing from the package. `validation.py` imports `exceptions`. `models.py` imports `exceptions` and `validation`. `loader.py` imports `exceptions`, `models` and `validation`. `analysis.py` imports only `validation`; it does not import `models.py` and works on any object with the same attributes as a `RecordingSession`. `reporting.py` imports `analysis` and `exceptions`. `cli.py` imports `analysis`, `exceptions`, `loader` and `reporting`; it is the only module that depends on every layer. No module imports `cli.py`, and `print` is used only in `cli.py`.

## Installation and running

The program is written for **Python 3.8 or later** (no newer syntax is used) and was tested with Python 3.11 and 3.14. There are no packages to install. First get the project and go into its folder:

```bash
git clone https://github.com/CLOBISO/ACIT4420-Assignment-II.git
cd ACIT4420-Assignment-II
```

From a zip copy instead, unzip it and go into the extracted folder (on Windows: right-click, **Extract All**):

```bash
unzip podcast-recording-analyzer.zip
cd podcast-recording-analyzer
```

Run all commands from this folder (the one that holds `main.py`), because the default paths are relative.

```bash
python3 main.py
```

This is the same as the explicit form:

```bash
python3 main.py --profiles data/speakers.csv --sessions data/recording_sessions.csv data/recording_sessions_invalid.csv --output output
```

On Windows, or any system where the command is `python` rather than `python3`:

```bash
python main.py
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--profiles` | `data/speakers.csv` | The speaker profiles file. |
| `--sessions` | `data/recording_sessions.csv data/recording_sessions_invalid.csv` | One or more session files. |
| `--output` | `output` | Directory for the report files. Created if it does not exist. |
| `-h`, `--help` | | Shows the usage text. |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | The reports were written. Rejected rows are expected and do not cause a failure. |
| 1 | The profiles file cannot be read, or none of the session files can be read, or the output cannot be written. A one-line `Error: ...` is printed to standard error. No traceback is shown for these cases. |
| 2 | Wrong command-line usage (reported by `argparse`). |

A session file that cannot be read is skipped and listed under "Files not processed". The run only stops if no session file could be read.

### One session file or all of them

The example command in section 7 of the assignment text, `python main.py --sessions data/recording_sessions.csv`, works, but it processes only the valid file (25 rows, 5 recordings, nothing rejected). The default command, and the two-file form shown above, also read `data/recording_sessions_invalid.csv`, which section 4.1 requires. Use one of those to see the rejected-row handling. Any file name that ends in `.csv` is accepted, for example `recording_sessions (1).csv` from a browser download.

### Tests

```bash
python3 -m unittest discover -s tests -t .      # or: python -m unittest discover -s tests -t .
```

See Testing for what the tests cover.

## Input data

| File | Content |
|---|---|
| `data/speakers.csv` | Three speakers with their usual pitch, energy, speech rate and pause ratio. |
| `data/recording_sessions.csv` | 25 valid windows in five recordings. |
| `data/recording_sessions_invalid.csv` | 11 windows, one valid and ten with deliberate problems. |
| `tests/fixtures/recording_sessions_extra.csv` | Not part of the official data and not read by default. Extra test input for two further recordings and two rejected rows. See Extra test data. |

The column names are used exactly as supplied (`DATA_DICTIONARY.txt` lists them). A file with a missing required column, or an empty file, is rejected as a whole.

**Row numbering.** The CSV header is row 1, so the first data row is row 2. This is the line number a spreadsheet shows. Only truly blank lines are skipped, and they are still counted in the numbering. A line whose fields are all empty (such as `,,,,,,,,,`) is not blank: it is rejected as "(row): every field is empty" and reported.

## Class design

| Class | Responsibility |
|---|---|
| `AcousticProfile` | A speaker's usual pitch, energy, speech rate and pause ratio. Each value is range-checked when it is set. |
| `Speaker` | A validated speaker ID, a name and an `AcousticProfile`. |
| `SourceRow` | Where a record came from: file name and row number (a `namedtuple`). |
| `AcousticWindow` | One window with typed values (int timestamp, bool `speech_present`, float features). It decides its own `status` (`usable`, `no speech` or `unreliable`), its `warnings` and its `exclusion_reason`. |
| `RecordingSession` | One recording: a validated recording ID, one `Speaker` and its windows, keyed by timestamp. Gives sorted, usable, no-speech, unreliable, excluded and flagged windows. |
| `RejectedRecord` | A rejected row: file name, row number, all `(field, reason)` problems and the raw values. |
| `LoadResult` | What the session loader returns: sessions, rejected rows, file problems and row counts. |
| `RecordingLoader` | Reads one or more session files, validates rows, groups them by recording ID and links them to speakers. |
| `Assessment` | Base class for one way of interpreting a recording. Defines `evaluate()` and a shared result format. |
| `StyleAssessment` | Subclass: speaking-style label and reasons. |
| `QualityAssessment` | Subclass: quality score, band and reasons. |
| `SessionAnalyzer` | Runs the calculations and every assessment and builds the result dictionary. |
| `ReportWriter` | Creates the output directory and writes the three files. |

### Where each OOP concept is demonstrated

- **Composition**
  - `Speaker` has an `AcousticProfile`.
  - `RecordingSession` has a `Speaker` and a collection of `AcousticWindow` objects.
  - `SessionAnalyzer` has a list of `Assessment` objects.
  - `LoadResult` holds `RecordingSession` and `RejectedRecord` objects.
- **Encapsulation**
  - `AcousticProfile` keeps its values in protected attributes (`_pitch`, ...) behind properties with validating setters, so an impossible value cannot be stored.
  - `AcousticWindow`, `Speaker`, `RejectedRecord` and `LoadResult` keep their data in protected attributes and expose read-only properties. `LoadResult` returns copies.
  - `RecordingSession._windows` can only grow through `add_window()`, which accepts only `AcousticWindow` objects and refuses a duplicate timestamp. The `windows` property returns a sorted tuple.
- **Inheritance and polymorphism**
  - `StyleAssessment` and `QualityAssessment` inherit from `Assessment` and override `evaluate()` and `name`. The base `evaluate()` raises `NotImplementedError`.
  - `SessionAnalyzer` calls `evaluate()` on each assessment without knowing its type. A new assessment can be added without changing the analyzer.
  - The exceptions are subclasses of built-in ones: `InvalidIdentifierError` and `InvalidRecordError` inherit from `ValueError`; `DataFileError` inherits from `Exception`.
- **Class methods and static methods**
  - `QualityAssessment.score()` is a **static method**. The formula belongs to the assessment but needs no instance state, and the tests can call it directly.
  - `AcousticProfile._checked()` and `RecordingLoader._identifier()` are also static methods, and so is `ReportWriter._write()`.
  - Assignment I used class methods (`from_dict`, `from_data`) to build objects from dictionaries. In this version the loader builds the objects from CSV rows, so those class methods are no longer needed and none are used.

## Requirement checklist

Items follow sections 4 and 6 of the assignment text.

| Requirement | Where it is met |
|---|---|
| 4.1 `with open(..., encoding="utf-8", newline="")` and the `csv` module | Reading: `loader.read_csv` (`csv.reader`). Writing: `reporting.ReportWriter._write` opens every output file; `ReportWriter.write_summary` supplies the `csv.writer` for the summary CSV. |
| 4.1 Load profiles and both session files | `loader.load_speakers`, `loader.RecordingLoader.load`; the defaults in `cli.py` name all three files. |
| 4.1 Convert values to proper types | `validation.parse_timestamp` (int), `parse_bool` (bool), `parse_float` (finite float); `AcousticWindow` checks the types again. |
| 4.1 Group by recording ID | `RecordingLoader._accept` adds each row to a `RecordingSession` in `self._sessions`, keyed by recording ID. |
| 4.1 Connect each recording to an existing speaker | `RecordingLoader._speaker` looks the ID up in the speakers dictionary. If the first accepted row of a recording belongs to one speaker, rows with another speaker are rejected. |
| 4.2 Regular expressions with full match | `validation.SPEAKER_ID_PATTERN` (`S\d{3}`), `RECORDING_ID_PATTERN` (`REC-\d{4}-\d{3}`), `CSV_FILENAME_PATTERN` (any ordinary file name ending in `.csv`); all used with `fullmatch` in `_validate_identifier` and `validate_csv_filename`. Numeric ranges are never checked with a regex; `check_range` compares numbers. |
| 4.3 Missing fields and unexpected row length | `validation._required_text` ("is missing"); `loader._row_values` ("every field is empty" for a row of empty cells, "expected 10 values, found 9" for a wrong length). |
| 4.3 Values that cannot be converted | `parse_int`, `parse_float`, `parse_bool` (exactly `True` or `False`). `parse_float` also rejects `nan` and `inf`. |
| 4.3 Impossible or out-of-range values | `validation.check_range` with `FEATURE_LIMITS` (inclusive limits). |
| 4.3 Unknown speaker | `RecordingLoader._speaker`, which handles the `KeyError`. |
| 4.3 Poor signal quality, documented rule | `validation.UNRELIABLE_QUALITY_BELOW`, `LOW_QUALITY_BELOW`, `HIGH_NOISE_ABOVE`; applied in `AcousticWindow.status` and `.warnings`. See Validation rules. |
| 4.3 `speech_present` is False | `RecordingLoader._accept` (contradiction check) and `AcousticWindow.status` (`no speech`). |
| 4.3 Source file, row, field and reason for every rejected row | `RejectedRecord` and `reporting.format_rejections`. Every problem in a row is listed, not only the first. |
| 4.4 At least two custom exceptions, raised and handled | `InvalidIdentifierError`, `InvalidRecordError`, `DataFileError`. See the table below. |
| 4.4 `FileNotFoundError`, `PermissionError`, `ValueError`, `KeyError`, `csv.Error` | See the try/except table below. `UnicodeDecodeError`, `IsADirectoryError` and `OSError` are handled as well. |
| 4.4 Useful error messages | Messages name the field, the value and the expected format or range. File errors name the path. |
| 4.4 No empty except, no broad `except Exception` | Every `except` names specific exception classes and either records the problem or raises a `DataFileError` with context. |
| 4.5 Reuse and improve the Assignment I analysis | `analysis.py`: same thresholds and rule order as Assignment I. |
| 4.5 Insufficient data kept apart from a real result | `status` in the result dictionary and the `status` column in the CSV. See Analysis rules. |
| 4.6 Output directory created if missing | `ReportWriter.__init__` calls `mkdir(parents=True, exist_ok=True)`. |
| 4.6 Three output files | `analysis_summary.csv`, `analysis_report.txt`, `rejected_records.txt` (`ReportWriter.write_all`). |
| 4.6 Predictable re-runs | Files are opened with `"w"`, so they are overwritten. Output has no timestamps and a fixed order. |
| 6 Package with at least three meaningful modules | `podcast_analyzer/` has seven modules besides `__init__.py`. |
| 6 Classes, encapsulation, composition | See Class design. |
| 6 At least three targeted try/except structures | Thirteen `try` blocks, listed below. |
| 6 At least two regular-expression validations | Speaker ID and recording ID, plus the file name check. |
| 6 Two input files read, two output files written | Three input files, three output files. |
| 6 `pathlib` | `Path` is used in `loader`, `exceptions`, `reporting` and `cli`; `validation.validate_csv_filename` receives a `Path` and checks its `.name`. Output paths use the `/` operator. No absolute paths are written in the code. |
| 6 Structured result | `SessionAnalyzer.analyze()` returns one dictionary per recording. |
| 6 Tests: valid, invalid, missing-file, boundary | `tests/`. See Testing. |
| 6 Standard library only | `csv`, `re`, `math`, `statistics`, `argparse`, `pathlib`, `collections`, `io`, `sys`; the tests add `unittest`, `tempfile`, `contextlib` and `shutil`. |
| 7 Run from the project folder, completion summary | `python3 main.py`; the summary is printed by `cli.format_summary`. It gives the files read, the accepted and rejected rows and the files created. |

### Custom exceptions

There are exactly three: `InvalidIdentifierError(ValueError)`, `InvalidRecordError(ValueError)` and `DataFileError(Exception)`. `InvalidIdentifierError` keeps `.field` and `.value`, `InvalidRecordError` keeps `.problems` (every `(field, reason)` pair of the row) and `DataFileError` keeps `.path` and `.reason`.

| Exception | Raised in | Handled in |
|---|---|---|
| `InvalidIdentifierError` (also a `ValueError`) | `validation._validate_identifier`, via `validate_speaker_id` and `validate_recording_id` | `RecordingLoader._identifier` and `loader._valid_recording_id`. In `load_speakers` it is caught by `_parse_into` as a `ValueError`. |
| `InvalidRecordError` (also a `ValueError`) | `loader._row_values` (every field empty, or wrong row length), `loader._parse_speaker` and `RecordingLoader._accept` (any problems found in the row), `RecordingSession.add_window` (duplicate timestamp) | `loader.load_speakers` and `RecordingLoader._load_row`, which turn it into a `RejectedRecord` and continue with the next row. |
| `DataFileError` (a plain `Exception`) | `validation.validate_csv_filename` (called by `read_csv`), `loader.read_csv`, `ReportWriter.__init__` and `ReportWriter._write`. `RecordingLoader.load` also creates one, without raising it, for a file listed twice and records it as a file problem. | `RecordingLoader.load` for session files (the file is skipped); `cli.main` for everything else (message and exit code 1). |

### Targeted try/except blocks

| # | Where | Catches | What it does |
|---|---|---|---|
| 1 | `validation.parse_int` | `ValueError` | Re-raises with the field name and the value. |
| 2 | `validation.parse_float` | `ValueError` | Re-raises with the field name and the value. |
| 3 | `loader.read_csv` | `FileNotFoundError`, `IsADirectoryError`, `PermissionError`, `UnicodeDecodeError`, `csv.Error` | Raises `DataFileError` with the path and a readable reason. |
| 4 | `loader._parse_into` | `ValueError` | Records the problem and returns `None`, so all problems of a row are collected. |
| 5 | `loader.load_speakers` | `InvalidRecordError` | Rejects the speaker row and continues. |
| 6 | `RecordingLoader.load` | `DataFileError` | Records a file problem and moves on to the next file. |
| 7 | `RecordingLoader._load_row` | `InvalidRecordError` | Rejects the row and continues. |
| 8 | `RecordingLoader._identifier` | `InvalidIdentifierError` | Records the problem for the row. |
| 9 | `RecordingLoader._speaker` | `KeyError` | Records "unknown speaker" for the row. |
| 10 | `loader._valid_recording_id` | `InvalidIdentifierError` | Returns `None` so a rejected row is not counted as a valid recording. |
| 11 | `ReportWriter.__init__` | `FileExistsError`, `NotADirectoryError`, `PermissionError`, `OSError` | Raises `DataFileError` for the output directory. |
| 12 | `ReportWriter._write` | `IsADirectoryError`, `PermissionError`, `OSError` | Raises `DataFileError` for the output file. |
| 13 | `cli.main` | `DataFileError` | Prints `Error: ...` to standard error and returns 1. |

## Validation rules

Valid ranges (inclusive) are the Assignment I ranges: pitch 45-450 Hz, energy 0-1, speech rate 30-260, pause ratio 0-1, background noise 0-1, signal quality 0-1. The same ranges are used for the baselines in `speakers.csv`.

| Rule | Result |
|---|---|
| Every field of the row is empty (for example `,,,,,,,,,`) | Rejected row: "(row): every field is empty". Only a truly blank line is skipped. |
| Row has a different number of values than the header | Rejected row |
| `recording_id` does not match `REC-\d{4}-\d{3}`, or `speaker_id` does not match `S\d{3}` | Rejected row |
| `speaker_id` is well formed but not in `speakers.csv` | Rejected row |
| The recording already belongs to a different speaker | Rejected row |
| Duplicate timestamp within a recording | Rejected row |
| `timestamp` is not a whole number of 0 or more | Rejected row |
| `speech_present` is anything other than exactly `True` or `False` (after trimming spaces), such as `true`, `TRUE`, `yes` or `1` | Rejected row |
| `background_noise` or `signal_quality` is missing, not a number, or outside 0-1 | Rejected row |
| `speech_present` is True and a speech feature is missing, not a number, `nan`/`inf`, or out of range | Rejected row |
| `speech_present` is False and any of pitch, energy, speech rate or pause ratio has a value | Rejected row (the row contradicts itself) |
| `speech_present` is False and the four speech values are empty | Accepted. Status `no speech`: excluded from the speech features. |
| `speech_present` is True and signal quality is below 0.35 | Accepted. Status `unreliable`: excluded from the speech features. |
| Signal quality from 0.35 up to (not including) 0.60 | Accepted and used, flagged as low signal quality |
| Background noise above 0.60 | Accepted and used, flagged as high background noise |
| Bad row in `speakers.csv` (bad ID, missing name, bad or out-of-range baseline, duplicate ID) | Rejected row. Recordings of that speaker then have an unknown speaker. |
| Missing, unreadable, non-UTF-8 or empty file, a file name that does not end in `.csv` (any other ordinary name such as `recording_sessions (1).csv` is accepted), or a file with missing required columns | File problem. A session file is skipped; the speakers file stops the run. |
| A recording has fewer than 3 accepted windows | Accepted. Its quality is reported as "insufficient data" with no score (see Recording quality). |

### Signal-quality rule

A window is a valid measurement even if its quality is poor, so a poor window is not a rejected row. The rule decides how it is used:

- **Below 0.35: unreliable.** The window is accepted and counted. It is excluded from the speech analysis (pitch, energy, speech rate, pause ratio), because those values cannot be trusted. It still counts for the background noise and signal quality averages and for the window total, so the quality score reflects it.
- **0.35 up to below 0.60: flagged.** The window is used for everything and listed as flagged.
- **Background noise above 0.60: flagged**, in the same way.

Flags only explain why a quality score is lower. Excluded windows (no speech, unreliable) are listed as excluded and are not also flagged.

### Windows without speech

A window with `speech_present` False has no speech values to analyse. If the four speech columns are empty, it is accepted and excluded from the speech features, but it still counts for noise, signal quality and the window total. If any of those columns holds a value, the row is rejected with the reason "the row contradicts itself": it is not possible to tell whether the flag or the values are wrong.

## Analysis rules

Thresholds are taken from `analysis.py`.

### Summaries

- Pitch, energy, speech rate and pause ratio are summarised (mean, minimum, maximum, sample standard deviation) over **usable** windows.
- Background noise and signal quality use **every accepted window**, including no-speech and unreliable ones.
- Each speech feature is compared with the speaker's usual value, as a percentage for pitch and speech rate and as a difference for energy and pause ratio.

### Speaking style (first matching rule wins)

1. **Insufficient data:** fewer than 3 usable windows, or less than 50% of the windows are usable.
2. **Noise affected:** average background noise is 0.50 or more, or average signal quality is below 0.70. Checked before the style rules because noise inflates measured energy and pitch.
3. **Temporarily varied:** pitch varies by more than 8% around its mean, speech rate by more than 12%, or the energy standard deviation is above 0.08. Checked before energetic and deliberate because only an uneven session has a large spread.
4. **Energetic:** energy is at least 0.10 above usual, and either the speech rate is at least 10% faster or the pitch is at least 7% higher.
5. **Deliberate:** speech rate is at least 12% slower than usual, and the pause ratio is at least 0.08 higher.
6. **Consistent:** none of the rules above apply.

The energetic, deliberate and consistent rules compare values rounded to the precision shown in the report (energy and pause ratio 2 decimals, percentages 1 decimal), so the decisions match the printed changes. The noise and variation rules use unrounded values.

### Recording quality

`score = 100 x (0.5 x mean signal quality + 0.3 x (1 - mean background noise) + 0.2 x share of usable windows)`, rounded to one decimal.

| Score | Band |
|---|---|
| 75 or more | good |
| 55 to under 75 | acceptable |
| below 55 | poor |

If fewer than half the windows are usable, a "good" band is lowered to **acceptable**.

Two cases get no score:

- **Fewer than 3 windows in the recording** (`QualityAssessment.MIN_WINDOWS_FOR_SCORE`, counting every accepted window, not only the usable ones). The label is "insufficient data", the score is empty and the reason reads, for example, "only 1 window; at least 3 are needed for a quality score". A single clean window would otherwise score "good". REC-2026-101 is an example.
- **No valid noise or quality values.** The label is "cannot be evaluated".

### Insufficient data is kept separate

Every result dictionary has a `status` key, and the summary CSV has a `status` column:

- `insufficient data` when the style label is "insufficient data";
- `analysed` for every other label, including "consistent" and "noise affected".

So a recording with too little usable speech is never reported as "normal". The style column also says "insufficient data" for these recordings. A quality score is still calculated when the recording has at least 3 windows (REC-2026-005 has 5, so it scores 69.0), but the score does not make the recording "analysed". With fewer than 3 windows (REC-2026-101) the quality is "insufficient data" as well and the `quality_score` cell is empty. The feature means shown for such a recording are based on the few usable windows and should not be read as a result.

## Output files

All three files are written to the output directory (`output/` by default). The directory is created if missing. Files are opened for writing, so a re-run overwrites them and does not append. The output contains no timestamps, recordings are sorted by recording ID, and rejected rows are sorted by file name and then row number. Two runs on the same input give byte-identical files (checked with `md5sum`).

| File | Content |
|---|---|
| `analysis_summary.csv` | A header and one row per recording, sorted by recording ID. Columns: `recording_id`, `speaker_id`, `source_files` (joined with `;`), `total_windows`, `usable_windows`, `no_speech_windows`, `unreliable_windows`, `flagged_windows`, `status`, `style`, `quality_band`, `quality_score`, `mean_pitch`, `pitch_change_pct`, `mean_energy`, `energy_change`, `mean_speech_rate`, `speech_rate_change_pct`, `mean_pause_ratio`, `pause_ratio_change`, `mean_background_noise`, `mean_signal_quality`. Fixed decimals; an empty cell when there is no value. |
| `analysis_report.txt` | A header block (the same lines as the console summary: speaker profiles, session files read, files not processed, row counts and recording counts; then the recordings where every row was rejected), then one block per recording: window counts, feature table, excluded windows, flagged windows, style and quality with reasons. |
| `rejected_records.txt` | A header with the number of rejected rows (`Rows rejected: 10 (0 in speakers.csv, 10 in session files)`), the files that were not processed, then one block per rejected row: file name, row number, one `- field: reason` line per problem and the raw values. A reason that already starts with the field name is shown without repeating it (`- pitch: is missing`). |

## Results on the official data

Run: 3 speaker profiles accepted (0 rejected); 36 session rows read, 26 accepted, 10 rejected; 6 recordings, 4 analysed and 2 with insufficient data.

| Recording | Speaker | Status | Speaking style | Quality |
|---|---|---|---|---|
| REC-2026-001 | S001 | analysed | consistent | good (96.3) |
| REC-2026-002 | S002 | analysed | energetic | good (94.7) |
| REC-2026-003 | S003 | analysed | deliberate | good (96.0) |
| REC-2026-004 | S001 | analysed | noise affected | acceptable (64.3) |
| REC-2026-005 | S002 | insufficient data | insufficient data | acceptable (69.0) |
| REC-2026-101 | S001 | insufficient data | insufficient data | insufficient data (no score) |

REC-2026-005 has 3 no-speech windows, so only 2 of 5 windows are usable. REC-2026-101 has one accepted window, because the other rows of that recording in the invalid file were rejected; with fewer than 3 windows it gets no quality score. REC-2026-102 and REC-2026-103 have no accepted rows, so they are not analysed; they are listed under "Every row rejected" in the report.

### Rejected rows in `recording_sessions_invalid.csv`

| Row | Field | Reason |
|---|---|---|
| 3 | `speech_present` | must be True or False, got 'yes' |
| 4 | `speaker_id` | '001' is not a valid speaker ID |
| 5 | `recording_id` | 'REC-26-102' is not a valid recording ID |
| 6 | `speaker_id` | unknown speaker 'S999' (not in speakers.csv) |
| 7 | `timestamp`, `pitch` | timestamp: must be a whole number, got 'two'; pitch: must be a number, got 'high' |
| 8 | `energy`, `pause_ratio` | energy: -0.2 is outside the valid range 0-1; pause_ratio: 1.2 is outside the valid range 0-1 |
| 9 | `speech_rate`, `background_noise`, `signal_quality` | speech_rate: -30.0 is outside the valid range 30-260; background_noise: -0.1 is outside the valid range 0-1; signal_quality: 1.3 is outside the valid range 0-1 |
| 10 | `speech_present` | is False but pitch, energy, speech_rate, pause_ratio contain values; the row contradicts itself |
| 11 | `pitch` | is missing |
| 12 | `(row)` | expected 10 values, found 9 |

Row 2 is the only accepted row in this file.

## Example output

Console summary from `python main.py` (exit code 0):

```text
Podcast Voice and Recording Analyzer
Speaker profiles:     speakers.csv (3 accepted, 0 rejected)
Session files read:   recording_sessions.csv, recording_sessions_invalid.csv
Files not processed:  none
Session rows:         36 read, 26 accepted, 10 rejected
Recordings:           6 (4 analysed, 2 insufficient data)
Reports written:
  output/analysis_summary.csv
  output/analysis_report.txt
  output/rejected_records.txt
```

The first lines of `output/analysis_report.txt` repeat these counts and add the recordings where every row was rejected:

```text
Podcast Voice and Recording Analyzer - analysis report
==========================================================================
Speaker profiles:     speakers.csv (3 accepted, 0 rejected)
Session files read:   recording_sessions.csv, recording_sessions_invalid.csv
Files not processed:  none
Session rows:         36 read, 26 accepted, 10 rejected
Recordings:           6 (4 analysed, 2 insufficient data)
Every row rejected:   REC-2026-102, REC-2026-103
Rejected rows:        listed in rejected_records.txt
```

Three rows of `output/analysis_summary.csv` (the header line is shortened here):

```text
recording_id,speaker_id,source_files,total_windows,usable_windows,no_speech_windows,unreliable_windows,flagged_windows,status,style,quality_band,quality_score,...
REC-2026-002,S002,recording_sessions.csv,5,5,0,0,0,analysed,energetic,good,94.7,129.8,10.0,0.54,0.18,141.0,30.6,0.13,-0.12,0.10,0.95
REC-2026-005,S002,recording_sessions.csv,5,2,3,0,2,insufficient data,insufficient data,acceptable,69.0,120.0,1.7,0.36,0.00,108.5,0.5,0.25,0.00,0.12,0.69
REC-2026-101,S001,recording_sessions_invalid.csv,1,1,0,0,0,insufficient data,insufficient data,insufficient data,,148.0,0.0,0.42,0.00,126.0,0.0,0.19,0.00,0.08,0.97
```

One block from `output/analysis_report.txt`. REC-2026-101, which has a single window, ends instead with "Recording quality: INSUFFICIENT DATA" and the reason "only 1 window; at least 3 are needed for a quality score":

```text
==========================================================================
REC-2026-005  |  speaker S002  |  insufficient data
Source: recording_sessions.csv
--------------------------------------------------------------------------
Windows: 5 total, 2 usable, 3 no speech, 0 unreliable, 2 flagged

Feature                Mean     Min     Max   Stdev   Usual   Change
--------------------------------------------------------------------
Pitch (Hz)            120.0   119.0   121.0     1.4   118.0    +1.7%
Energy                 0.36    0.35    0.37    0.01    0.36    +0.00
Speech rate (wpm)     108.5   107.0   110.0     2.1   108.0    +0.5%
Pause ratio            0.25    0.24    0.26    0.01    0.25    +0.00
Background noise       0.12    0.10    0.13    0.01
Signal quality         0.69    0.35    0.92    0.30

Excluded windows (not used for the speech features)
  t=0    no speech detected
  t=1    no speech detected
  t=3    no speech detected
Flagged windows (still used)
  t=2    low signal quality 0.38
  t=4    low signal quality 0.35

Speaking style: INSUFFICIENT DATA
  - only 2 of 5 windows are usable; at least 3 and at least 50% are needed
Recording quality: ACCEPTABLE (69.0/100)
  - average signal quality 0.69 (50% of the score)
  - average background noise 0.12 (30% of the score, lower is better)
  - 2 of 5 windows usable (20% of the score)
  - 2 usable window(s) flagged for low quality or high noise
  - 69.0 is in the 'acceptable' band (good >= 75, acceptable >= 55, otherwise poor)
```

The top of `output/rejected_records.txt`, and three of its blocks:

```text
Rejected records
==========================================================================
Rows rejected: 10 (0 in speakers.csv, 10 in session files)
Row numbers are CSV line numbers: the header is row 1, the first data row is row 2.

Files not processed:
  none

recording_sessions_invalid.csv, row 7
  - timestamp: must be a whole number, got 'two'
  - pitch: must be a number, got 'high'
  raw: REC-2026-102,S002,two,True,high,0.40,115,0.22,0.10,0.94

recording_sessions_invalid.csv, row 11
  - pitch: is missing
  raw: REC-2026-103,S003,1,True,,0.49,145,0.15,0.09,0.96

recording_sessions_invalid.csv, row 12
  - (row): expected 10 values, found 9
  raw: REC-2026-103,S003,2,True,178,0.50,146,0.14,0.10
```

If a file cannot be read, the program prints one line and returns 1, for example `Error: no session file could be read (nope.csv: file not found)`.

## Extra test data

PDF section 3 allows additional files for your own tests. `tests/fixtures/recording_sessions_extra.csv` has the same ten columns as the official session files and uses the three official speakers from `data/speakers.csv`. It is not read by default. It holds 13 data rows:

- **REC-2026-201** (S001): six clean windows (noise at most 0.10, signal quality 0.94 or better). The pitch has a burst in the middle (186 and 192 Hz around a usual 148), while energy, speech rate and pause ratio stay near the baseline. Result: **temporarily varied**, because pitch varies by 13.0% around its mean (limit 8%).
- **REC-2026-202** (S003): five windows, three of them with speech but signal quality 0.30, 0.25 and 0.20. Those three are **unreliable** and excluded, so only 2 of 5 windows are usable and the style is **insufficient data**. The quality is still scored, because the recording has 5 windows (acceptable, 61.7).
- **Two rejected rows:** row 8 has `speech_present` written as `true` (not exactly `True`), and row 9 is `,,,,,,,,,` (every field empty).

Run it together with the two official session files. The output goes to a separate directory so that `output/` keeps the results for the official data:

```bash
python main.py --sessions data/recording_sessions.csv data/recording_sessions_invalid.csv tests/fixtures/recording_sessions_extra.csv --output output/extra
```

```text
Podcast Voice and Recording Analyzer
Speaker profiles:     speakers.csv (3 accepted, 0 rejected)
Session files read:   recording_sessions.csv, recording_sessions_invalid.csv, recording_sessions_extra.csv
Files not processed:  none
Session rows:         49 read, 37 accepted, 12 rejected
Recordings:           8 (5 analysed, 3 insufficient data)
Reports written:
  output/extra/analysis_summary.csv
  output/extra/analysis_report.txt
  output/extra/rejected_records.txt
```

The two rejected rows of the fixture appear in `output/extra/rejected_records.txt` as:

```text
recording_sessions_extra.csv, row 8
  - speech_present: must be True or False, got 'true'
  raw: REC-2026-201,S001,6,true,149,0.42,126,0.19,0.08,0.96

recording_sessions_extra.csv, row 9
  - (row): every field is empty
  raw: ,,,,,,,,,
```

The report block of REC-2026-202 shows the unreliable windows:

```text
Windows: 5 total, 2 usable, 0 no speech, 3 unreliable, 0 flagged
...
Excluded windows (not used for the speech features)
  t=1    signal quality 0.30 is below 0.35 (unreliable)
  t=2    signal quality 0.25 is below 0.35 (unreliable)
  t=3    signal quality 0.20 is below 0.35 (unreliable)

Speaking style: INSUFFICIENT DATA
  - only 2 of 5 windows are usable; at least 3 and at least 50% are needed
```

## Testing

The 170 tests in `tests/` use the standard-library `unittest` module. They all pass on Python 3.11 and on Python 3.14. There are five test files:

| File | Tests | Covers |
|---|---|---|
| `tests/test_validation.py` | 32 | Identifier and file-name patterns, type conversion, ranges, the exception classes. |
| `tests/test_models.py` | 27 | `AcousticProfile`, `Speaker`, `AcousticWindow` and `RecordingSession`. |
| `tests/test_loader.py` | 40 | Loading speakers and sessions, rejected rows, file problems, the official data and the extra fixture. |
| `tests/test_analysis.py` | 50 | Calculations, style rules, quality rules, the analyzer, the official data and the extra fixture. |
| `tests/test_cli.py` | 21 | Exit codes, console summary, output files, reruns, the one-file command and the extra fixture. |

File tests write only to temporary directories and never change `data/`. Run them from the project folder (the one that holds `main.py`):

```bash
python3 -m unittest discover -s tests -t .
```

They cover four kinds of case:

- **Valid:** well-formed profiles and sessions load, group by recording ID and analyse to the expected labels. A session file named `recording_sessions (1).csv` is accepted, and so is the command with only `data/recording_sessions.csv`.
- **Invalid:** bad identifiers, unconvertible values, out-of-range values, unknown speakers, wrong row length, contradictory `speech_present` rows, `speech_present` other than exactly `True` or `False`, and rows with every field empty are rejected with the right field and reason.
- **Missing or unusable files:** a missing file, a directory, an empty file, missing columns, non-UTF-8 input and a name that does not end in `.csv` give a `DataFileError` or a file problem, and a bad session file does not stop the other files.
- **Boundary:** values exactly on the range limits, signal quality at 0.35 and 0.60, noise at 0.60, the style and quality thresholds, and the minimum of 3 windows for a quality score.

The extra fixture is tested in `test_loader.py`, `test_analysis.py` and `test_cli.py`: the 11 accepted and 2 rejected rows, the temporarily varied result for REC-2026-201, the three unreliable windows of REC-2026-202, and the full command with the two official files.

## Known limitations

- **Heuristic thresholds.** The thresholds are rules of thumb tuned on simulated data. Real recordings would need recalibration.
- **Small sessions.** The official recordings have 5 windows (one has 1). With so few windows, a small number of unusual windows has a large effect on the spread, so the labels are less stable than for longer sessions. Recordings with fewer than 3 usable windows get the style "insufficient data", and recordings with fewer than 3 windows in total get no quality score.
- **One label only.** The first matching rule wins. A noisy session that is also energetic is reported only as noise affected.
- **No time structure.** "Temporarily varied" is based on spread only. It does not say when the change happened, and window order is not used.
- **One stored profile per speaker.** The usual profile is taken as given and is not updated from new sessions.
- **A rejected row is dropped.** If a row of a recording is rejected, the recording is analysed from its remaining rows. The report lists the rejection, but the analysis of that recording does not mention it.
- **Simulated data and personal data.** No real audio is used. The speaker names are read and validated, but they are never written to any output: reports and rejected records use speaker IDs only, and in a rejected `speakers.csv` row the name is replaced by `[name withheld]`. This follows data minimisation. Real voice features linked to a named speaker could be personal data (possibly biometric data) under GDPR, so real use would need a data-protection review.
