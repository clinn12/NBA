"""Provide stable project-root imports and file paths for command-line scripts.

Front Matter
------------
Project: NBA Data Collection
File type: Python module
Status: Active
Last updated: 2026-08-14

Purpose: make scripts behave identically when launched inside or outside the
project directory by adding the repository root to ``sys.path`` once.
Usage: scripts import ``PROJECT_ROOT`` or call ``project_path`` before importing
the ``nba_simulator`` package or resolving default data/output locations.
"""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def project_path(*parts: str) -> Path:
    """Return an absolute path beneath the project root."""

    return PROJECT_ROOT.joinpath(*parts)
