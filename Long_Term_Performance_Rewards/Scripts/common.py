"""Shared project helpers.

Front Matter
------------
Project: NBA Long-Term Performance Rewards
File type: Python module
Status: Active
Last updated: 2026-08-15

Purpose
-------
Resolve analysis configuration and paths consistently for scripts and notebooks.

Usage
-----
Import ``load_config`` and ``configured_path`` from report-generation code.

This module centralizes path and configuration handling so every script agrees
on the same project root, config file, and relative-path behavior. That matters
because the project is used from notebooks, direct scripts, and the pipeline
runner; without one path convention, outputs can silently land in the wrong
folder depending on the current working directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANALYSIS_CONFIG_PATH = PROJECT_ROOT / "Config" / "analysis_settings.json"


def load_config(config_path: str | Path = DEFAULT_ANALYSIS_CONFIG_PATH) -> dict[str, Any]:
    """Load the JSON pipeline configuration.

    Why it matters:
        Project behavior should be controlled by `Config/analysis_settings.json` rather
        than scattered hard-coded values. This makes thresholds, paths, and
        season-processing rules visible to humans and AI agents.
    """
    path = Path(config_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def project_path(relative_path: str | Path) -> Path:
    """Resolve a project-relative path against the repository root."""
    path = Path(relative_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def configured_path(config: dict[str, Any], key: str) -> Path:
    """Return a configured project path from the `paths` section."""
    return project_path(config["paths"][key])


def ensure_parent_dir(path: Path) -> None:
    """Create the parent folder for an output path if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
