"""Pull and publish historical NBA regular-season standings.

Front Matter
------------
Project: NBA Data Collection
File type: Python script
Status: Active
Last updated: 2026-08-15

Purpose
-------
Retrieve Basketball Reference standings, preserve raw HTML by season, validate
the normalized table, and update the shared historical publication.

Usage
-----
Run ``python scripts/pull_historical_standings.py`` from any directory. The
default config publishes to ``data/published/historical/nba_standings.csv``.

This script retrieves Basketball Reference regular-season standings and updates
the governed shared publication. It exists so standings refreshes are repeatable from
the command line instead of depending on manually running notebook cells.

Why it matters:
    The downstream reward/penalty reports depend on complete, typed, validated
    regular-season data. If standings are malformed, non-playoff and low-win
    penalty outputs become unreliable.

Important behavior:
    By default, completed-season mode avoids pulling an active incomplete season.
    The script validates required columns, numeric fields, duplicate teams, and
    empty scrape results before writing to disk.
"""

from __future__ import annotations

import argparse
import string
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_collection.historical_results import (
    DEFAULT_CONFIG_PATH,
    configured_path,
    load_config,
    write_publication_manifest,
)


def get_last_standings_year(completed_only: bool = True, today: date | None = None) -> int:
    """Return the last standings season that should be considered for pulling.

    Why it matters:
        Basketball Reference can expose active-season pages before a season is
        complete. Completed-only mode protects the historical dataset from
        partial seasons unless the config explicitly allows them.
    """
    today = today or date.today()

    if today.month >= 10:
        active_season_year = today.year + 1
    else:
        active_season_year = today.year

    if not completed_only:
        return active_season_year

    if today.month >= 10:
        return active_season_year - 1

    return active_season_year


def load_existing_data(file_path, min_size_kb=1):
    """Load the existing standings CSV and return its already-processed years."""
    file_path = Path(file_path)
    if file_path.exists() and file_path.stat().st_size > (min_size_kb * 1024):
        df = pd.read_csv(file_path)
        return df, set(df["Year"].unique())

    return pd.DataFrame(), set()


def fetch_standings_html(year: int, timeout: int = 30, raw_path: Path | None = None) -> BeautifulSoup:
    """Load cached raw HTML or retrieve and preserve one standings page."""

    if raw_path and raw_path.is_file():
        return BeautifulSoup(raw_path.read_text(encoding="utf-8"), features="html.parser")
    url = f"https://www.basketball-reference.com/leagues/NBA_{year}_standings.html"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error while fetching {url}: {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error while fetching {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Timed out while fetching {url}") from exc

    if raw_path:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(html, encoding="utf-8")
    return BeautifulSoup(html, features="html.parser")


def parse_standings(soup: BeautifulSoup, year: int) -> pd.DataFrame:
    """Convert a standings HTML page into a validated analysis-ready DataFrame.

    Important behavior:
        Conference labels are inferred from Basketball Reference header rows and
        forward-filled to team rows. Numeric conversion happens here so report
        logic can sort and compare values safely.
    """
    headers = [th.getText() for th in soup.findAll("tr", limit=2)[0].findAll("th")][:8]
    rows = soup.findAll("tr")[1:]
    standings = [
        [tr.getText() for tr in rows[i].findAll(["th", "td"])]
        for i in range(len(rows))
    ]

    if year >= 1971:
        standings = [lst for lst in standings if len(lst) == 8]

    df = pd.DataFrame(standings, columns=headers)
    df.columns = ["Team", "W", "L", "WL_pct", "GB", "PPG", "OPPG", "SRS"]
    df["Year"] = year
    df["GB"] = df["GB"].replace({"\u2014": 0, "\u00e2\u20ac\u201d": 0, "-": 0})

    invalid_chars = string.punctuation
    df["Team"] = df["Team"].str.strip(invalid_chars)
    df["Team"] = df["Team"].str.replace(r"\*.*$", "", regex=True).str.strip()
    df["Team"] = df["Team"].str.replace(r"\s*\(\d+\)\s*$", "", regex=True).str.strip()
    df["Conference"] = df["Team"].where(
        df["Team"].isin(["Eastern Conference", "Western Conference", "Eastern Division", "Western Division"])
    )
    df["Conference"] = df["Conference"].ffill()
    df = df[~df["Team"].str.contains(r"Conference|Division", na=False, case=False)]
    df = df[df["W"].notna()]
    df = df[df["W"] != "W"]
    df = df.drop_duplicates(subset=["Team"])

    numeric_columns = ["W", "L", "WL_pct", "GB", "PPG", "OPPG", "SRS"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    required_columns = ["Team", "W", "L", "WL_pct", "GB", "PPG", "OPPG", "SRS", "Year", "Conference"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required standings columns for {year}: {missing_columns}")

    null_columns = [column for column in required_columns if df[column].isna().any()]
    if null_columns:
        raise ValueError(f"Null values found in required standings columns for {year}: {null_columns}")

    if df.empty:
        raise ValueError(f"No standings rows parsed for {year}")

    if not df["Team"].is_unique:
        duplicate_teams = df.loc[df["Team"].duplicated(), "Team"].tolist()
        raise ValueError(f"Duplicate teams found in standings for {year}: {duplicate_teams}")

    return df[required_columns]


def update_standings(config: dict | None = None, *, write_manifest: bool = True) -> pd.DataFrame:
    """Update the configured standings CSV with any missing eligible seasons."""
    config = config or load_config(DEFAULT_CONFIG_PATH)
    file_path = configured_path(config, "standings")
    file_path.parent.mkdir(parents=True, exist_ok=True)

    start_year = int(config["start_year"])
    completed_only = bool(config["processing"].get("standings_completed_only", True))
    timeout = int(config["processing"].get("request_timeout_seconds", 30))
    reuse_raw = bool(config["processing"].get("reuse_raw_html", True))
    raw_root = configured_path(config, "raw_root") / "standings"
    last_year = get_last_standings_year(completed_only=completed_only)

    existing_df, existing_years = load_existing_data(file_path, min_size_kb=1)
    new_data_added = False

    for year in range(start_year, last_year + 1):
        if year in existing_years:
            print(f"Skipping {year} - already processed.")
            continue

        print(f"Processing {year}...")
        raw_path = raw_root / f"NBA_{year}_standings.html" if reuse_raw else None
        soup = fetch_standings_html(year, timeout=timeout, raw_path=raw_path)
        standings_df = parse_standings(soup, year)
        existing_df = pd.concat([existing_df, standings_df], ignore_index=True)
        new_data_added = True

    if not new_data_added:
        print("No new standings data found. Existing file was not changed.")
        if write_manifest:
            write_publication_manifest(config)
        return existing_df

    existing_df = existing_df.drop_duplicates(subset=["Year", "Team"], keep="last")
    existing_df = existing_df.sort_values(by=["Year", "Conference", "W"], ascending=[False, False, False])
    existing_df.to_csv(file_path, index=False)
    if write_manifest:
        write_publication_manifest(config)
    print(f"Updated {file_path}")
    return existing_df


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Pull NBA regular season standings.")
    parser.add_argument("--config", default=None, help="Path to a data-pull JSON config file.")
    args = parser.parse_args()
    config = load_config(args.config or DEFAULT_CONFIG_PATH)
    update_standings(config)


if __name__ == "__main__":
    main()
