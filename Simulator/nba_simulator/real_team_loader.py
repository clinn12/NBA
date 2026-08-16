"""Load pulled real-team profiles into the simulator's team factory interface.

Front Matter
------------
Project: NBA Simulator
File type: Python module
Status: Active
Last updated: 2026-08-01

Purpose: validate a canonical real-team JSON payload and translate one selected
team into the keyword arguments expected by the simulator's ``create_team``.
Usage: call ``load_real_team_payload`` once, then ``build_real_team`` for each
requested abbreviation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict


def load_real_team_payload(path: str | Path) -> Dict[str, Any]:
    """Read and minimally validate a canonical real-team profile JSON file."""

    source = Path(path).resolve()
    with source.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    payload["_source_path"] = str(source)
    return payload


def build_real_team(payload: Dict[str, Any], abbreviation: str, create_team: Callable[..., Any]) -> Any:
    """Build one TeamState using the notebook's existing create_team function."""
    code = abbreviation.upper()
    team = next((item for item in payload["teams"] if item["abbreviation"] == code), None)
    if team is None:
        raise KeyError(f"{code} is not present in the real-team payload")
    roster_specs = [(player["name"], player["role"], player["overrides"]) for player in team["roster"]]
    result = create_team(team["name"], roster_specs)
    result.dataset_metadata = dict(payload.get("metadata", {}))
    result.dataset_source_path = payload.get("_source_path")
    source_path = Path(payload["_source_path"]) if payload.get("_source_path") else None
    variability = source_path.parent / "historical_variability_2025-26_regular_season.json" if source_path else None
    result.default_variability_path = str(variability) if variability and variability.exists() else None
    return result
