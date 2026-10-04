"""Podcast Voice and Recording Analyzer: run from the repository root.

    python main.py
    python main.py --profiles data/speakers.csv --sessions data/recording_sessions.csv data/recording_sessions_invalid.csv --output output
"""

import sys

from podcast_analyzer.cli import main

if __name__ == "__main__":
    sys.exit(main())
