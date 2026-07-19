"""Generate NBA reward and penalty eligibility reports.

This script is the analytical core of the project. It loads validated standings
and playoff data, normalizes franchise names, derives reward/penalty cohorts,
applies configured streak and window rules, and writes both detailed CSV outputs
and AI-readable metadata.

Why it matters:
    The project is not just producing tables; it is encoding a policy-analysis
    framework. Documentation here makes the business meaning of each output
    visible so future humans and AI agents can interpret results without
    reverse-engineering the notebook history.

Important behavior:
    - Franchise lineage is controlled by `Data/team_mapping.csv`.
    - Streak and window reports use non-overlapping logic.
    - `Report_Manifest.json` is the preferred file for agent-level context
      about report criteria, source files, and methodology.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from .common import DEFAULT_ANALYSIS_CONFIG_PATH, configured_path, ensure_parent_dir, load_config
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from common import DEFAULT_ANALYSIS_CONFIG_PATH, configured_path, ensure_parent_dir, load_config


REPORT_DEFINITIONS = {
    "Output_Playoff_Streaks.csv": {
        "category": "Reward",
        "subject": "Playoff appearances",
        "description": "Teams that reached the playoffs in consecutive seasons for the configured streak length.",
        "interpretation": "These teams may qualify for a long-term performance reward based on sustained playoff participation.",
    },
    "Output_Playoff_Windows.csv": {
        "category": "Reward",
        "subject": "Playoff appearances",
        "description": "Teams that reached the playoffs the configured number of times within the configured year window.",
        "interpretation": "These teams may qualify for a long-term performance reward based on repeated playoff participation within a broader window.",
    },
    "Output_Championship_Streaks.csv": {
        "category": "Reward",
        "subject": "NBA championships",
        "description": "Teams that won NBA championships in consecutive seasons for the configured streak length.",
        "interpretation": "These teams may qualify for the strongest long-term performance reward based on consecutive championships.",
    },
    "Output_Championship_Windows.csv": {
        "category": "Reward",
        "subject": "NBA championships",
        "description": "Teams that won the configured number of NBA championships within the configured year window.",
        "interpretation": "These teams may qualify for a long-term performance reward based on multiple championships in a compact period.",
    },
    "Output_Conference_Championship_Streaks.csv": {
        "category": "Reward",
        "subject": "Conference championships",
        "description": "Teams that won conference championships in consecutive seasons for the configured streak length.",
        "interpretation": "These teams may qualify for a reward based on repeated Finals appearances.",
    },
    "Output_Conference_Championship_Windows.csv": {
        "category": "Reward",
        "subject": "Conference championships",
        "description": "Teams that won the configured number of conference championships within the configured year window.",
        "interpretation": "These teams may qualify for a reward based on repeated deep playoff success within a broader period.",
    },
    "Output_Non_Playoff_Streaks.csv": {
        "category": "Penalty",
        "subject": "Missed playoffs",
        "description": "Teams that missed the playoffs in consecutive seasons for the configured streak length.",
        "interpretation": "These teams may qualify for a long-term performance penalty based on sustained non-playoff results.",
    },
    "Output_Non_Playoff_Windows.csv": {
        "category": "Penalty",
        "subject": "Missed playoffs",
        "description": "Teams that missed the playoffs the configured number of times within the configured year window.",
        "interpretation": "These teams may qualify for a penalty based on repeated missed playoffs within a broader period.",
    },
    "Output_Lowest_Win_Streaks.csv": {
        "category": "Penalty",
        "subject": "Lowest regular-season win totals among non-playoff teams",
        "description": "Teams that finished among the configured number of lowest-win non-playoff teams in consecutive seasons.",
        "interpretation": "These teams may qualify for a penalty based on repeatedly being among the league's lowest-performing non-playoff teams.",
    },
    "Output_Lowest_Win_Windows.csv": {
        "category": "Penalty",
        "subject": "Lowest regular-season win totals among non-playoff teams",
        "description": "Teams that finished among the configured number of lowest-win non-playoff teams the configured number of times within the configured year window.",
        "interpretation": "These teams may qualify for a penalty based on repeated low-win non-playoff seasons within a broader period.",
    },
}


COLUMN_DEFINITIONS = {
    "Team": "Current normalized franchise name after applying Data/team_mapping.csv.",
    "Streak_Begin": "First season year in a qualifying consecutive streak.",
    "Streak_End": "Final season year in a qualifying consecutive streak.",
    "Window_Start": "First qualifying season year used in a non-overlapping window result.",
    "Window_End": "Final qualifying season year used in a non-overlapping window result.",
    "Count": "Number of qualifying seasons included in the window. This equals the configured streak threshold.",
    "Years_In_Window": "List of specific season years that caused the team to qualify within the window.",
    "Parameter": "Report-generation setting name from the analysis config.",
    "Value": "Value used for a report-generation setting.",
}


def validate_positive_integer(name: str, value: int) -> None:
    """Validate threshold values before they influence report logic."""
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer. Received: {value}")


def thresholds_from_config(config: dict) -> dict[str, int]:
    """Translate config threshold names into analysis variable names.

    Why it matters:
        The config uses user-facing names, while the report logic uses explicit
        internal names. This function is the controlled bridge between them.
    """
    thresholds = config["thresholds"]
    values = {
        "playoff_streak_threshold": int(thresholds["playoff_streak"]),
        "playoff_window_threshold": int(thresholds["playoff_window"]),
        "champ_streak_threshold": int(thresholds["championship_streak"]),
        "champ_window_threshold": int(thresholds["championship_window"]),
        "conference_champ_streak_threshold": int(thresholds["conference_championship_streak"]),
        "conference_champ_window_threshold": int(thresholds["conference_championship_window"]),
        "non_playoff_streak_threshold": int(thresholds["non_playoff_streak"]),
        "non_playoff_window_threshold": int(thresholds["non_playoff_window"]),
        "count_lowest_win_teams": int(thresholds["lowest_win_team_count"]),
        "lowest_win_streak_threshold": int(thresholds["lowest_win_streak"]),
        "lowest_win_window_threshold": int(thresholds["lowest_win_window"]),
    }

    for name, value in values.items():
        validate_positive_integer(name, value)

    return values


def validate_required_columns(df: pd.DataFrame, required_columns: list[str], dataframe_name: str) -> None:
    """Ensure a source DataFrame contains the fields required downstream."""
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"{dataframe_name} is missing required columns: {missing_columns}")


def validate_no_duplicate_team_years(df: pd.DataFrame, dataframe_name: str) -> None:
    """Guard against duplicated team-season rows before cohort derivation."""
    duplicates = df[df.duplicated(subset=["Team", "Year"], keep=False)]
    if not duplicates.empty:
        duplicate_preview = duplicates[["Team", "Year"]].drop_duplicates().head(10).to_dict("records")
        raise ValueError(f"{dataframe_name} contains duplicate Team/Year rows: {duplicate_preview}")


def validate_source_data(standings: pd.DataFrame, playoffs: pd.DataFrame, team_mapping: pd.DataFrame) -> None:
    """Validate source files before applying reward and penalty rules.

    Why it matters:
        The output reports are only interpretable if each input has one record
        per team-season and the columns used for ranking, matching, and flags
        are numeric where expected.
    """
    standings_required_columns = ["Year", "Team", "Conference", "W", "L", "WL_pct", "GB", "PPG", "OPPG", "SRS"]
    playoffs_required_columns = ["Year", "Team", "Wins", "Champion", "Conference_Champion"]
    mapping_required_columns = ["Source_Team", "Mapped_Team", "Start_Year", "End_Year"]

    validate_required_columns(standings, standings_required_columns, "standings_df")
    validate_required_columns(playoffs, playoffs_required_columns, "playoffs_df")
    validate_required_columns(team_mapping, mapping_required_columns, "team_mapping_df")

    for column in ["Year", "W", "L", "WL_pct", "GB", "PPG", "OPPG", "SRS"]:
        standings[column] = pd.to_numeric(standings[column], errors="coerce")

    for column in ["Year", "Wins", "Champion", "Conference_Champion"]:
        playoffs[column] = pd.to_numeric(playoffs[column], errors="coerce")

    for column in ["Start_Year", "End_Year"]:
        team_mapping[column] = pd.to_numeric(team_mapping[column], errors="coerce")

    standings_null_columns = [column for column in standings_required_columns if standings[column].isna().any()]
    playoffs_null_columns = [column for column in playoffs_required_columns if playoffs[column].isna().any()]
    mapping_null_columns = [
        column for column in ["Source_Team", "Mapped_Team"]
        if team_mapping[column].isna().any()
    ]

    if standings_null_columns:
        raise ValueError(f"standings_df has null values in required columns: {standings_null_columns}")

    if playoffs_null_columns:
        raise ValueError(f"playoffs_df has null values in required columns: {playoffs_null_columns}")

    if mapping_null_columns:
        raise ValueError(f"team_mapping_df has null values in required columns: {mapping_null_columns}")

    validate_no_duplicate_team_years(standings, "standings_df")
    validate_no_duplicate_team_years(playoffs, "playoffs_df")


def apply_team_mapping(df: pd.DataFrame, team_mapping: pd.DataFrame) -> pd.DataFrame:
    """Normalize historical franchise names using editable mapping rules.

    Important behavior:
        Mapping rules can be unconditional or bounded by start/end season years.
        This keeps debatable franchise-lineage decisions visible in data rather
        than hidden as hard-coded transformations.
    """
    mapped_df = df.copy()

    for _, row in team_mapping.iterrows():
        mask = mapped_df["Team"].eq(row["Source_Team"])

        if pd.notna(row["Start_Year"]):
            mask = mask & mapped_df["Year"].ge(row["Start_Year"])

        if pd.notna(row["End_Year"]):
            mask = mask & mapped_df["Year"].le(row["End_Year"])

        mapped_df.loc[mask, "Team"] = row["Mapped_Team"]

    return mapped_df


def build_streaks_non_overlapping(data: pd.DataFrame, streak_length: int) -> pd.DataFrame:
    """Identify consecutive, non-overlapping qualifying streaks by team.

    Why it matters:
        Non-overlapping streaks prevent a single dynasty or prolonged slump from
        being counted repeatedly with highly similar start/end years.
    """
    output_columns = ["Team", "Streak_Begin", "Streak_End"]

    if data.empty:
        return pd.DataFrame(columns=output_columns)

    df = data[["Team", "Year"]].dropna().drop_duplicates().copy()
    df["Year"] = df["Year"].astype(int)
    df = df.sort_values(["Team", "Year"]).reset_index(drop=True)
    df["Year_Diff"] = df.groupby("Team")["Year"].diff().fillna(1)
    df["Break"] = df["Year_Diff"] > 1
    df["Run_ID"] = df.groupby("Team")["Break"].cumsum()

    results = []
    for (team, run_id), group in df.groupby(["Team", "Run_ID"]):
        years = group["Year"].tolist()
        idx = 0

        while idx + streak_length <= len(years):
            results.append({
                "Team": team,
                "Streak_Begin": years[idx],
                "Streak_End": years[idx + streak_length - 1],
            })
            idx += streak_length

    if not results:
        return pd.DataFrame(columns=output_columns)

    return (
        pd.DataFrame(results, columns=output_columns)
        .sort_values(["Team", "Streak_Begin"])
        .reset_index(drop=True)
    )


def find_window_nonoverlap(data: pd.DataFrame, streak: int, window: int) -> pd.DataFrame:
    """Identify non-overlapping qualifying windows by team.

    Important behavior:
        A window is inclusive. For example, 5 qualifying seasons from 2000 to
        2006 fit inside a 7-year window.
    """
    output_columns = ["Team", "Window_Start", "Window_End", "Count", "Years_In_Window"]

    if data.empty:
        return pd.DataFrame(columns=output_columns)

    df = data[["Team", "Year"]].dropna().copy()
    df["Year"] = df["Year"].astype(int)
    df = df.drop_duplicates().sort_values(["Team", "Year"])

    results = []
    for team, group in df.groupby("Team", sort=False):
        years = group["Year"].tolist()
        idx = 0

        while idx < len(years):
            if idx + streak - 1 < len(years):
                candidate_years = years[idx: idx + streak]

                if candidate_years[-1] - candidate_years[0] <= window - 1:
                    results.append({
                        "Team": team,
                        "Window_Start": candidate_years[0],
                        "Window_End": candidate_years[-1],
                        "Count": streak,
                        "Years_In_Window": candidate_years,
                    })
                    idx += streak
                    continue

            idx += 1

    if not results:
        return pd.DataFrame(columns=output_columns)

    return (
        pd.DataFrame(results, columns=output_columns)
        .sort_values(["Team", "Window_Start"])
        .reset_index(drop=True)
    )


def prepare_report_inputs(config: dict, thresholds: dict[str, int]) -> dict[str, pd.DataFrame]:
    """Load source files and derive the base cohorts used by reports."""
    standings_df = pd.read_csv(configured_path(config, "standings"))
    playoffs_df = pd.read_csv(configured_path(config, "playoffs"))
    team_mapping_df = pd.read_csv(configured_path(config, "team_mapping"))

    validate_source_data(standings_df, playoffs_df, team_mapping_df)
    common_years = sorted(set(standings_df["Year"]).intersection(set(playoffs_df["Year"])))
    if not common_years:
        raise ValueError("No overlapping seasons found between standings and playoff data")

    standings_df = standings_df[standings_df["Year"].isin(common_years)].copy()
    playoffs_df = playoffs_df[playoffs_df["Year"].isin(common_years)].copy()
    standings_df = apply_team_mapping(standings_df, team_mapping_df)
    playoffs_df = apply_team_mapping(playoffs_df, team_mapping_df)

    playoff_teams = playoffs_df[["Year", "Team", "Wins", "Champion", "Conference_Champion"]].copy()
    champ_teams = playoff_teams[playoff_teams["Champion"] == 1].copy()
    conference_champ_teams = playoff_teams[playoff_teams["Conference_Champion"] == 1].copy()

    non_playoff_teams = pd.merge(
        standings_df,
        playoff_teams,
        on=["Team", "Year"],
        how="left",
        indicator=True,
    )
    non_playoff_teams = non_playoff_teams[non_playoff_teams["_merge"] == "left_only"].copy()
    non_playoff_teams = non_playoff_teams[["Year", "Team", "Conference", "W", "L", "WL_pct", "GB", "PPG", "OPPG", "SRS"]]

    lowest_win_teams = non_playoff_teams.sort_values(["Year", "WL_pct"]).copy()
    lowest_win_teams = lowest_win_teams.groupby("Year").head(thresholds["count_lowest_win_teams"]).copy()

    return {
        "playoff_teams": playoff_teams,
        "champ_teams": champ_teams,
        "conference_champ_teams": conference_champ_teams,
        "non_playoff_teams": non_playoff_teams,
        "lowest_win_teams": lowest_win_teams,
    }


def build_report_specs(inputs: dict[str, pd.DataFrame], thresholds: dict[str, int]) -> dict[str, dict]:
    """Define every report in one place.

    Why it matters:
        Centralizing report specs makes it easier to audit criteria and reduces
        the chance that generation, saving, and metadata drift from each other.
    """
    return {
        "Output_Playoff_Streaks.csv": {
            "data": inputs["playoff_teams"], "report_type": "streak",
            "streak": thresholds["playoff_streak_threshold"], "window": None,
        },
        "Output_Playoff_Windows.csv": {
            "data": inputs["playoff_teams"], "report_type": "window",
            "streak": thresholds["playoff_streak_threshold"], "window": thresholds["playoff_window_threshold"],
        },
        "Output_Championship_Streaks.csv": {
            "data": inputs["champ_teams"], "report_type": "streak",
            "streak": thresholds["champ_streak_threshold"], "window": None,
        },
        "Output_Championship_Windows.csv": {
            "data": inputs["champ_teams"], "report_type": "window",
            "streak": thresholds["champ_streak_threshold"], "window": thresholds["champ_window_threshold"],
        },
        "Output_Conference_Championship_Streaks.csv": {
            "data": inputs["conference_champ_teams"], "report_type": "streak",
            "streak": thresholds["conference_champ_streak_threshold"], "window": None,
        },
        "Output_Conference_Championship_Windows.csv": {
            "data": inputs["conference_champ_teams"], "report_type": "window",
            "streak": thresholds["conference_champ_streak_threshold"],
            "window": thresholds["conference_champ_window_threshold"],
        },
        "Output_Non_Playoff_Streaks.csv": {
            "data": inputs["non_playoff_teams"], "report_type": "streak",
            "streak": thresholds["non_playoff_streak_threshold"], "window": None,
        },
        "Output_Non_Playoff_Windows.csv": {
            "data": inputs["non_playoff_teams"], "report_type": "window",
            "streak": thresholds["non_playoff_streak_threshold"], "window": thresholds["non_playoff_window_threshold"],
        },
        "Output_Lowest_Win_Streaks.csv": {
            "data": inputs["lowest_win_teams"], "report_type": "streak",
            "streak": thresholds["lowest_win_streak_threshold"], "window": None,
        },
        "Output_Lowest_Win_Windows.csv": {
            "data": inputs["lowest_win_teams"], "report_type": "window",
            "streak": thresholds["lowest_win_streak_threshold"], "window": thresholds["lowest_win_window_threshold"],
        },
    }


def build_criteria_text(spec: dict) -> str:
    """Create plain-language criteria text for summaries and metadata."""
    definition = REPORT_DEFINITIONS[spec["file_name"]]

    if spec["report_type"] == "streak":
        return (
            f"{definition['subject']}: at least {spec['streak']} consecutive qualifying seasons. "
            "Streak results are non-overlapping."
        )

    return (
        f"{definition['subject']}: at least {spec['streak']} qualifying seasons within "
        f"{spec['window']} inclusive years. Window results are non-overlapping."
    )


def format_report_instances(report_df: pd.DataFrame, report_type: str) -> list[str]:
    """Format report rows for the AI-facing README.

    Why it matters:
        The individual CSVs remain the source of truth, but the README should be
        readable on its own. Listing every qualifying instance under the right
        analysis section lets an AI agent understand the report contents without
        opening multiple CSV files first.
    """
    if report_df.empty:
        return ["No qualifying teams found for this report."]

    lines = []
    for _, row in report_df.iterrows():
        if report_type == "streak":
            lines.append(f"- {row['Team']}: {int(row['Streak_Begin'])}-{int(row['Streak_End'])}")
        else:
            lines.append(
                f"- {row['Team']}: {int(row['Window_Start'])}-{int(row['Window_End'])}; "
                f"count={int(row['Count'])}; years={row['Years_In_Window']}"
            )

    return lines


def write_ai_readable_outputs(
    reports_dir,
    report_specs: dict[str, dict],
    reports: dict[str, pd.DataFrame],
    thresholds: dict[str, int],
) -> None:
    """Write metadata files that explain the reports to humans and AI agents."""
    data_dictionary_rows = []
    for column, definition in COLUMN_DEFINITIONS.items():
        data_dictionary_rows.append({"Column": column, "Definition": definition})

    pd.DataFrame(data_dictionary_rows).to_csv(reports_dir / "Report_Data_Dictionary.csv", index=False)

    manifest = {
        "project": "NBA Long-Term Performance Rewards",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Identify NBA teams that may qualify for long-term rewards or penalties based on "
            "sustained performance patterns."
        ),
        "source_files": {
            "standings": "Data/nba_standings.csv",
            "playoffs": "Data/nba_playoffs.csv",
            "team_mapping": "Data/team_mapping.csv",
            "analysis_config": "Config/analysis_settings.json",
        },
        "thresholds": thresholds,
        "methodology": {
            "streak_reports": "Consecutive qualifying seasons are split into non-overlapping streak chunks.",
            "window_reports": "Qualifying seasons are grouped into non-overlapping windows when the threshold count fits within the configured inclusive year span.",
            "team_names": "Historical franchise names are normalized using Data/team_mapping.csv before report generation.",
            "season_alignment": "Reports only use seasons that exist in both standings and playoff source files, preventing incomplete newer standings from being treated as non-playoff seasons.",
        },
        "reports": [],
    }

    for file_name, spec in report_specs.items():
        definition = REPORT_DEFINITIONS[file_name]
        report_df = reports[file_name]
        manifest["reports"].append({
            "file": file_name,
            "category": definition["category"],
            "subject": definition["subject"],
            "report_type": spec["report_type"],
            "criteria": build_criteria_text({**spec, "file_name": file_name}),
            "description": definition["description"],
            "interpretation": definition["interpretation"],
            "rows": int(len(report_df)),
            "unique_teams": int(report_df["Team"].nunique()) if "Team" in report_df.columns else 0,
            "columns": list(report_df.columns),
        })

    with (reports_dir / "Report_Manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    markdown_lines = [
        "# NBA Long-Term Performance Rewards Reports",
        "",
        "These files identify NBA teams that may qualify for long-term rewards or penalties based on sustained performance patterns.",
        "",
        "## How To Read The Reports",
        "",
        "- Streak reports require consecutive qualifying seasons and use non-overlapping streak chunks.",
        "- Window reports require a configured number of qualifying seasons inside a configured inclusive year span.",
        "- Team names are normalized with `Data/team_mapping.csv` before reports are created.",
        "- `Report_Manifest.json` is the most complete machine-readable description of the outputs.",
        "- `Report_Data_Dictionary.csv` defines the columns used across reports.",
        "",
        "## Report Inventory",
        "",
    ]

    for file_name, spec in report_specs.items():
        definition = REPORT_DEFINITIONS[file_name]
        report_df = reports[file_name]
        markdown_lines.extend([
            f"### {file_name}",
            f"- Category: {definition['category']}",
            f"- Subject: {definition['subject']}",
            f"- Criteria: {build_criteria_text({**spec, 'file_name': file_name})}",
            f"- Rows: {len(report_df)}",
            f"- Unique teams: {report_df['Team'].nunique() if 'Team' in report_df.columns else 0}",
            f"- Interpretation: {definition['interpretation']}",
            "",
            "Qualifying teams and instances:",
            *format_report_instances(report_df, spec["report_type"]),
            "",
        ])

    (reports_dir / "README_For_AI_Agents.md").write_text("\n".join(markdown_lines), encoding="utf-8")


def generate_reports(config: dict | None = None) -> dict[str, pd.DataFrame]:
    """Generate all reports and AI-readable metadata from configured inputs."""
    config = config or load_config(DEFAULT_ANALYSIS_CONFIG_PATH)
    thresholds = thresholds_from_config(config)

    for window_name, streak_name in [
        ("playoff_window_threshold", "playoff_streak_threshold"),
        ("champ_window_threshold", "champ_streak_threshold"),
        ("conference_champ_window_threshold", "conference_champ_streak_threshold"),
        ("non_playoff_window_threshold", "non_playoff_streak_threshold"),
        ("lowest_win_window_threshold", "lowest_win_streak_threshold"),
    ]:
        if thresholds[window_name] < thresholds[streak_name]:
            thresholds[window_name] = thresholds[streak_name]

    inputs = prepare_report_inputs(config, thresholds)
    report_specs = build_report_specs(inputs, thresholds)
    reports_dir = configured_path(config, "reports_dir")
    reports_dir.mkdir(parents=True, exist_ok=True)

    reports = {}
    for file_name, spec in report_specs.items():
        if spec["report_type"] == "streak":
            reports[file_name] = build_streaks_non_overlapping(spec["data"], spec["streak"])
        elif spec["report_type"] == "window":
            reports[file_name] = find_window_nonoverlap(spec["data"], spec["streak"], spec["window"])
        else:
            raise ValueError(f"Unknown report type for {file_name}: {spec['report_type']}")

    for file_name, report_df in reports.items():
        output_path = reports_dir / file_name
        ensure_parent_dir(output_path)
        report_df.to_csv(output_path, index=False)

    report_parameters = pd.DataFrame([
        {"Parameter": name, "Value": value}
        for name, value in thresholds.items()
    ])
    report_parameters.to_csv(reports_dir / "Report_Parameters.csv", index=False)

    write_ai_readable_outputs(reports_dir, report_specs, reports, thresholds)
    print(f"Updated reports in {reports_dir}")
    return reports


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Generate NBA reward and punishment reports.")
    parser.add_argument("--config", default=None, help="Path to an analysis JSON config file.")
    args = parser.parse_args()
    config = load_config(args.config) if args.config else load_config(DEFAULT_ANALYSIS_CONFIG_PATH)
    generate_reports(config)


if __name__ == "__main__":
    main()
