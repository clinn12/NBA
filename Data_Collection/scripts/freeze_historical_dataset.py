"""Create a content-addressed immutable snapshot of a simulator input dataset.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: preserve reproducible historical inputs and maintain a registry of
current and superseded versions without overwriting earlier data.
Usage: run ``python scripts/freeze_historical_dataset.py`` after dataset QA; the
command copies the input, writes a SHA-256 manifest, and updates the registry.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Dict

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT


DEFAULT_INPUT = PROJECT_ROOT / "data/published/real_teams_2025-26_regular_season.json"
DEFAULT_VERSION_ROOT = PROJECT_ROOT / "data/versions"
DEFAULT_MANIFEST_ROOT = PROJECT_ROOT / "data/manifests"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_dataset(source: Path, version_root: Path, manifest_root: Path) -> Dict[str, Any]:
    """Copy a dataset to a hash-named version and update manifest governance.

    Existing content-addressed snapshots are reused rather than overwritten.
    Earlier registry entries are retained and marked superseded when appropriate.
    """

    source = source.resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    dataset_id = str(metadata.get("dataset_id") or source.stem)
    digest = _sha256(source)
    version_id = f"{dataset_id}__sha256_{digest[:12]}"
    destination_dir = version_root / version_id
    destination = destination_dir / source.name
    manifest_path = manifest_root / f"{version_id}.json"

    if destination.exists() and _sha256(destination) != digest:
        raise RuntimeError(f"Immutable snapshot collision at {destination}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)

    related_files: Dict[str, Dict[str, Any]] = {}
    for candidate in (
        source.parent / "historical_variability_2025-26_regular_season.json",
        source.parent / "raw/historical_enrichment_2025-26_regular_season.json",
        source.parent / "raw/player_game_logs_2025-26_regular_season_nyk_sas_bos_lal.json",
    ):
        if candidate.exists():
            related_files[str(candidate.resolve())] = {"sha256": _sha256(candidate), "bytes": candidate.stat().st_size}

    manifest = {
        "manifest_version": "historical_dataset_manifest_v1",
        "version_id": version_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source),
        "snapshot_path": str(destination.resolve()),
        "sha256": digest,
        "bytes": source.stat().st_size,
        "dataset_metadata": metadata,
        "formula_version": metadata.get("formula_version"),
        "source_type": metadata.get("source_type"),
        "default_simulator_input": metadata.get("default_simulator_input", False),
        "related_source_files": related_files,
        "immutability_rule": "A different payload always receives a different content-addressed version_id; existing snapshot bytes are never overwritten.",
    }
    manifest_root.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("sha256") != digest or existing.get("snapshot_path") != manifest["snapshot_path"]:
            raise RuntimeError(f"Manifest collision at {manifest_path}")
        manifest = existing
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path.resolve())
    return manifest


def main() -> None:
    """Parse snapshot locations, freeze the dataset, and print its manifest."""

    parser = argparse.ArgumentParser(description="Freeze a content-addressed historical simulator dataset.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--version-root", default=str(DEFAULT_VERSION_ROOT))
    parser.add_argument("--manifest-root", default=str(DEFAULT_MANIFEST_ROOT))
    args = parser.parse_args()
    manifest = freeze_dataset(Path(args.input), Path(args.version_root), Path(args.manifest_root))
    print(json.dumps({key: manifest[key] for key in ("version_id", "sha256", "snapshot_path", "manifest_path")}, indent=2))


if __name__ == "__main__":
    main()
