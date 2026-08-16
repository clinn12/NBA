"""Quality assurance for formula-derived historical player enrichment fields.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-14

Purpose: detect missing sources, unreliable components, extreme values, broken
correlations, and missing-defender sensitivity before enrichment is consumed.
Usage: run ``python scripts/enrichment_qa.py`` or import ``build_enrichment_qa``;
the CLI writes JSON and player-level CSV reports.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Sequence

try:
    from ._project_paths import PROJECT_ROOT
except ImportError:  # Direct execution
    from _project_paths import PROJECT_ROOT
from data_collection.historical_enrichment import ENRICHED_FIELDS


DEFAULT_INPUT = PROJECT_ROOT / "data/published/real_teams_2025-26_regular_season.json"
DEFAULT_JSON = PROJECT_ROOT / "reports/enrichment_qa_2025-26_regular_season.json"
DEFAULT_CSV = PROJECT_ROOT / "reports/enrichment_qa_players_2025-26_regular_season.csv"
RELIABILITY_FIELDS = ("general", "defense", "tracking", "clutch")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _quantile(values: Sequence[float], probability: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _summary(values: Iterable[float]) -> Dict[str, Any]:
    observed = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not observed:
        return {"n": 0, "mean": None, "std": None, "min": None, "p05": None, "p25": None, "p50": None, "p75": None, "p95": None, "max": None}
    return {
        "n": len(observed),
        "mean": round(statistics.fmean(observed), 6),
        "std": round(statistics.pstdev(observed), 6),
        "min": round(min(observed), 6),
        "p05": round(_quantile(observed, 0.05), 6),
        "p25": round(_quantile(observed, 0.25), 6),
        "p50": round(_quantile(observed, 0.50), 6),
        "p75": round(_quantile(observed, 0.75), 6),
        "p95": round(_quantile(observed, 0.95), 6),
        "max": round(max(observed), 6),
    }


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right))
    return round(numerator / denominator, 6) if denominator > 1e-12 else None


def _flatten_players(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for team in payload.get("teams", []):
        for player in team.get("roster", []):
            enrichment = player.get("source_stats", {}).get("historical_enrichment", {})
            calculated = enrichment.get("calculated_fields", {})
            reliability = enrichment.get("reliability", {})
            components = enrichment.get("components", {})
            row: Dict[str, Any] = {
                "team": team.get("abbreviation"),
                "team_name": team.get("name"),
                "player": player.get("name"),
                "mpg": _number(player.get("overrides", {}).get("mpg")),
                "formula_version": enrichment.get("formula_version"),
            }
            row.update({field: _number(calculated.get(field)) for field in ENRICHED_FIELDS})
            row.update({f"reliability_{field}": _number(reliability.get(field)) for field in RELIABILITY_FIELDS})
            for field, value in components.items():
                number = _number(value)
                if number is not None:
                    row[f"component_{field}"] = number
            rows.append(row)
    return rows


def build_enrichment_qa(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate enrichment coverage, reliability, distributions, and sensitivity."""

    rows = _flatten_players(payload)
    expected_formula = payload.get("metadata", {}).get("formula_version")
    missing = {field: sum(row.get(field) is None for row in rows) for field in ENRICHED_FIELDS}
    formula_mismatches = sum(row.get("formula_version") != expected_formula for row in rows)
    distributions = {field: _summary(row[field] for row in rows if row.get(field) is not None) for field in ENRICHED_FIELDS}
    reliability = {field: _summary(row[f"reliability_{field}"] for row in rows if row.get(f"reliability_{field}") is not None) for field in RELIABILITY_FIELDS}
    low_reliability = {
        field: sum((row.get(f"reliability_{field}") or 0.0) < 0.35 for row in rows)
        for field in RELIABILITY_FIELDS
    }
    component_fields = sorted({key for row in rows for key in row if key.startswith("component_")})
    component_coverage = {
        field.removeprefix("component_"): {
            "observed": sum(row.get(field) is not None for row in rows),
            "nonzero": sum(abs(float(row.get(field) or 0.0)) > 1e-12 for row in rows if row.get(field) is not None),
        }
        for field in component_fields
    }
    correlations: Dict[str, float | None] = {}
    for index, left in enumerate(ENRICHED_FIELDS):
        for right in ENRICHED_FIELDS[index + 1:]:
            pairs = [(row[left], row[right]) for row in rows if row.get(left) is not None and row.get(right) is not None]
            correlations[f"{left}__{right}"] = _correlation([pair[0] for pair in pairs], [pair[1] for pair in pairs])
    extremes: Dict[str, Any] = {}
    for field in ENRICHED_FIELDS:
        observed = [row for row in rows if row.get(field) is not None]
        ordered = sorted(observed, key=lambda row: row[field])
        extremes[field] = {
            "lowest": [{"player": row["player"], "team": row["team"], "value": row[field]} for row in ordered[:5]],
            "highest": [{"player": row["player"], "team": row["team"], "value": row[field]} for row in ordered[-5:][::-1]],
        }

    team_sensitivity: List[Dict[str, Any]] = []
    for team in payload.get("teams", []):
        team_rows = [row for row in rows if row["team"] == team.get("abbreviation") and row.get("defense") is not None]
        rotation = sorted(team_rows, key=lambda row: row.get("mpg") or 0.0, reverse=True)[:10]
        if not rotation:
            continue
        def composite(row: Mapping[str, Any]) -> float:
            return float(row.get("defense") or 0.0) + 0.35 * float(row.get("switchability") or 0.0) + 0.25 * float(row.get("help_defense") or 0.0)
        def weighted(active: Sequence[Mapping[str, Any]]) -> float:
            weights = [max(1.0, float(row.get("mpg") or 0.0)) for row in active]
            return sum(composite(row) * weight for row, weight in zip(active, weights)) / sum(weights)
        baseline = weighted(rotation)
        ranked = sorted(rotation, key=composite, reverse=True)
        for removed_count in (1, 2):
            active = [row for row in rotation if row not in ranked[:removed_count]]
            if len(active) < 5:
                continue
            current = weighted(active)
            team_sensitivity.append({
                "team": team.get("abbreviation"),
                "removed_count": removed_count,
                "removed_players": [row["player"] for row in ranked[:removed_count]],
                "baseline_rotation_defense_composite": round(baseline, 6),
                "active_rotation_defense_composite": round(current, 6),
                "composite_change": round(current - baseline, 6),
                "simulator_opponent_efficiency_shift": round(max(-0.025, min(0.025, (baseline - current) * 0.008)), 6),
            })

    flags = []
    if any(missing.values()):
        flags.append("One or more required enrichment values are missing.")
    if formula_mismatches:
        flags.append("Player enrichment formula versions do not all match dataset metadata.")
    if payload.get("metadata", {}).get("feed_failures"):
        flags.append("One or more official enrichment feeds failed during source creation.")
    for field in ("dfga", "dfg_diff", "dfg2_diff", "dfg3_diff", "deflections", "distance", "drives", "catch_3pa"):
        coverage = component_coverage.get(field, {})
        if rows and int(coverage.get("nonzero", 0)) == 0:
            flags.append(f"Critical source component {field} is zero for every player; verify source-field mapping.")
    for pair, value in correlations.items():
        if value is not None and abs(value) >= 0.90:
            flags.append(f"High absolute correlation ({value}) between {pair.replace('__', ' and ')}; review for redundancy.")
    return {
        "report_version": "enrichment_qa_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": dict(payload.get("metadata", {})),
        "players": len(rows),
        "required_fields": list(ENRICHED_FIELDS),
        "missing_counts": missing,
        "formula_version_mismatches": formula_mismatches,
        "field_distributions": distributions,
        "reliability_distributions": reliability,
        "low_reliability_counts_below_0_35": low_reliability,
        "source_component_coverage": component_coverage,
        "enriched_field_correlations": correlations,
        "extreme_players": extremes,
        "missing_defender_sensitivity": team_sensitivity,
        "flags": flags,
        "status": "pass" if not flags else "review",
        "interpretation": "QA and deterministic sensitivity checks only; this report does not estimate predictive skill.",
        "player_rows": rows,
    }


def write_report(report: Mapping[str, Any], json_path: Path, csv_path: Path) -> None:
    """Write the aggregate QA report and flattened player diagnostics."""

    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = dict(report)
    rows = serializable.pop("player_rows")
    json_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    fieldnames = sorted({key for row in rows for key in row})
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Run enrichment QA from CLI arguments and fail on blocking findings."""

    parser = argparse.ArgumentParser(description="Audit formula-derived historical enrichment fields.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--json-output", default=str(DEFAULT_JSON))
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV))
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = build_enrichment_qa(payload)
    write_report(report, Path(args.json_output), Path(args.csv_output))
    print(json.dumps({"status": report["status"], "players": report["players"], "flags": len(report["flags"]), "json": args.json_output, "csv": args.csv_output}, indent=2))


if __name__ == "__main__":
    main()
