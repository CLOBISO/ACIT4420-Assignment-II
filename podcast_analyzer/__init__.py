"""Podcast Voice and Recording Analyzer.

Loads speaker profiles and recording sessions from CSV files, validates every
row, analyses each recording against the speaker's usual voice and writes the
results to report files. Run it through main.py or podcast_analyzer.cli.main().
"""

__all__ = ["analysis", "cli", "exceptions", "loader", "models", "reporting", "validation"]
