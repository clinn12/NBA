"""Govern historical standings, playoff results, and franchise lineage.

Front Matter
------------
Project: NBA Data Collection
File type: Python module
Status: Active
Last updated: 2026-08-15

Purpose
-------
Provide shared path resolution, validation, hashing, and manifest creation for
the long-run NBA results datasets published to consumer projects.

Usage
-----
Retrieval scripts load ``configs/historical_results.json`` through this module,
then call ``write_publication_manifest`` after a successful refresh. Consumer
projects read only the resulting files beneath ``data/published/historical``.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "historical_results.json"

REQUIRED_COLUMNS = {
    "standings": {"Team", "W", "L", "WL_pct", "Year", "Conference"},
    "playoffs": {"Team", "Overall", "Year", "Wins", "Champion", "Conference_Champion"},
    "franchise_lineage": {"Source_Team", "Mapped_Team", "Start_Year", "End_Year"},
}


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the historical-results configuration from an absolute or project-relative path."""

    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    return json.loads(config_path.read_text(encoding="utf-8"))


def configured_path(config: dict[str, Any], key: str) -> Path:
    """Resolve a configured path against the Data Collection project root."""

    path = Path(config["paths"][key])
    return path if path.is_absolute() else PROJECT_ROOT / path


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for one publication artifact."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_csv(path: Path, required_columns: set[str]) -> dict[str, Any]:
    """Validate one publication CSV and summarize its schema and season span."""

    if not path.is_file():
        raise FileNotFoundError(f"Required historical publication is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing = sorted(required_columns.difference(columns))
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path.name} contains no data rows")

    years = sorted({int(float(row["Year"])) for row in rows if row.get("Year")}) if "Year" in columns else []
    return {
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": sha256_file(path),
        "rows": len(rows),
        "columns": columns,
        "first_year": years[0] if years else None,
        "last_year": years[-1] if years else None,
    }


def build_publication_manifest(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an auditable manifest for all historical-results publications."""

    config = config or load_config()
    artifacts = {
        key: inspect_csv(configured_path(config, key), required)
        for key, required in REQUIRED_COLUMNS.items()
    }
    return {
        "manifest_version": "historical_league_results_v1",
        "dataset_family": config["dataset_family"],
        "source": config["source"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "publication_root": "data/published/historical",
        "consumer_contract": "Consumers read published artifacts and do not import collection code.",
        "artifacts": artifacts,
    }


def write_publication_manifest(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate all publications and atomically replace their manifest."""

    config = config or load_config()
    manifest = build_publication_manifest(config)
    output_path = configured_path(config, "manifest")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(output_path)
    return manifest
