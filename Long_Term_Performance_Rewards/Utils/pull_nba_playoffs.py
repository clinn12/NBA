"""Pull and validate NBA playoff standings.

This script retrieves Basketball Reference playoff standings and updates
`Data/nba_playoffs.csv`. It replaces manual notebook execution with a repeatable
data pull that can be run alone or as part of the full pipeline.

Why it matters:
    Championship, conference championship, and playoff reward reports all depend
    on playoff data. The script validates champion flags so the downstream
    reports do not silently reason over incomplete or malformed playoff tables.

Important behavior:
    Basketball Reference stores some playoff tables inside HTML comments, so the
    parser intentionally searches comments for the first standings table.
"""

from __future__ import annotations

import argparse
import os
import string
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup, Comment

try:
    from .common import DEFAULT_DATA_PULL_CONFIG_PATH, configured_path, ensure_parent_dir, load_config
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from common import DEFAULT_DATA_PULL_CONFIG_PATH, configured_path, ensure_parent_dir, load_config


def get_last_playoff_year(completed_only: bool = True, today: date | None = None) -> int:
    """Return the last playoff season that should be considered for pulling."""
    today = today or date.today()

    if not completed_only:
        return today.year if today.month >= 5 else today.year - 1

    return today.year if today.month >= 7 else today.year - 1


def load_existing_data(file_path, min_size_kb=1):
    """Load the existing playoff CSV and return its already-processed years."""
    if os.path.exists(file_path) and os.path.getsize(file_path) > (min_size_kb * 1024):
        df = pd.read_csv(file_path)
        return df, set(df["Year"].unique())

    return pd.DataFrame(), set()


def fetch_playoff_html(year: int, timeout: int = 30) -> BeautifulSoup:
    """Fetch and parse a Basketball Reference playoff standings page."""
    url = f"https://www.basketball-reference.com/playoffs/NBA_{year}_standings.html"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        html = urlopen(request, timeout=timeout)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error while fetching {url}: {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error while fetching {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Timed out while fetching {url}") from exc

    return BeautifulSoup(html, features="html.parser")


def parse_playoff(soup: BeautifulSoup, year: int) -> pd.DataFrame:
    """Convert a playoff standings page into a validated DataFrame.

    Important behavior:
        For seasons through 1983, playoff structure differed from the modern
        16-team format. The parser uses conference matchup columns to infer
        champions and conference champions for those seasons.
    """
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    first_table_found = False
    rows = []
    headers = []

    for comment in comments:
        if "<table" in comment and not first_table_found:
            table_soup = BeautifulSoup(comment, "html.parser")
            table = table_soup.find("table")

            if table:
                first_table_found = True
                header_rows = table.find_all("tr")
                if len(header_rows) < 2:
                    raise ValueError(f"Playoff table for {year} does not contain the expected header rows")

                header_row = header_rows[1]
                headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

                for tr in header_rows[2:]:
                    cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                    if cells:
                        rows.append(cells)

            break

    if not first_table_found:
        raise ValueError(f"No playoff standings table found for {year}")

    if not rows:
        raise ValueError(f"No playoff rows parsed for {year}")

    df = pd.DataFrame(rows, columns=headers)
    if "Team" not in df.columns or "Overall" not in df.columns:
        raise ValueError(f"Missing required playoff columns for {year}: Team and Overall are required")

    df["Year"] = year
    invalid_chars = string.punctuation
    df["Wins"] = df["Overall"].str[:2]
    df["Wins"] = pd.to_numeric(df["Wins"].str.strip(invalid_chars), errors="coerce")

    if year <= 1983:
        conference_columns = ["E", "W"]
        missing_conference_columns = [column for column in conference_columns if column not in df.columns]
        if missing_conference_columns:
            raise ValueError(f"Missing pre-1984 conference columns for {year}: {missing_conference_columns}")

        df["E_Wins"] = pd.to_numeric(df["E"].str[:2].str.strip(invalid_chars), errors="coerce")
        df["E_Losses"] = pd.to_numeric(df["E"].str[-2:].str.strip(invalid_chars), errors="coerce")
        df["W_Wins"] = pd.to_numeric(df["W"].str[:2].str.strip(invalid_chars), errors="coerce")
        df["W_Losses"] = pd.to_numeric(df["W"].str[-2:].str.strip(invalid_chars), errors="coerce")
        df["E_Games"] = df["E_Wins"] + df["E_Losses"]
        df["W_Games"] = df["W_Wins"] + df["W_Losses"]
        df["Conference_Champion"] = np.where((df["E_Games"] >= 1) & (df["W_Games"] >= 1), 1, 0)
        df["Champion"] = np.where((df["E_Wins"] >= 4) & (df["W_Wins"] >= 4), 1, 0)
    else:
        max_wins = df["Wins"].max()
        second_max_wins = df["Wins"].nlargest(2).iloc[1]
        df["Champion"] = np.where(df["Wins"] >= max_wins, 1, 0)
        df["Conference_Champion"] = np.where(df["Wins"] >= second_max_wins, 1, 0)

    required_columns = ["Team", "Overall", "Year", "Wins", "Champion", "Conference_Champion"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required playoff columns for {year}: {missing_columns}")

    null_columns = [column for column in required_columns if df[column].isna().any()]
    if null_columns:
        raise ValueError(f"Null values found in required playoff columns for {year}: {null_columns}")

    if not df["Team"].is_unique:
        duplicate_teams = df.loc[df["Team"].duplicated(), "Team"].tolist()
        raise ValueError(f"Duplicate teams found in playoffs for {year}: {duplicate_teams}")

    if df["Champion"].sum() != 1:
        raise ValueError(f"Expected exactly one champion for {year}, found {int(df['Champion'].sum())}")

    if df["Conference_Champion"].sum() != 2:
        raise ValueError(
            f"Expected exactly two conference champions for {year}, found {int(df['Conference_Champion'].sum())}"
        )

    numeric_columns = ["Year", "Wins", "Champion", "Conference_Champion"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df


def update_playoffs(config: dict | None = None) -> pd.DataFrame:
    """Update the configured playoff CSV with any missing eligible seasons."""
    config = config or load_config(DEFAULT_DATA_PULL_CONFIG_PATH)
    file_path = configured_path(config, "playoffs")
    ensure_parent_dir(file_path)

    start_year = int(config["start_year"])
    completed_only = bool(config["processing"].get("playoffs_completed_only", True))
    timeout = int(config["processing"].get("request_timeout_seconds", 30))
    last_year = get_last_playoff_year(completed_only=completed_only)

    existing_df, existing_years = load_existing_data(file_path, min_size_kb=1)
    new_data_added = False

    for year in range(start_year, last_year + 1):
        if year in existing_years:
            print(f"Skipping {year} - already processed.")
            continue

        print(f"Processing {year}...")
        soup = fetch_playoff_html(year, timeout=timeout)
        playoff_df = parse_playoff(soup, year)
        existing_df = pd.concat([existing_df, playoff_df], ignore_index=True)
        new_data_added = True

    if not new_data_added:
        print("No new playoff data found. Existing file was not changed.")
        return existing_df

    existing_df = existing_df.drop_duplicates(subset=["Year", "Team"], keep="last")
    existing_df = existing_df.sort_values(
        by=["Year", "Champion", "Conference_Champion", "Wins"],
        ascending=[False, False, False, False],
    )
    existing_df.to_csv(file_path, index=False)
    print(f"Updated {file_path}")
    return existing_df


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Pull NBA playoff standings.")
    parser.add_argument("--config", default=None, help="Path to a data-pull JSON config file.")
    args = parser.parse_args()
    config = load_config(args.config) if args.config else load_config(DEFAULT_DATA_PULL_CONFIG_PATH)
    update_playoffs(config)


if __name__ == "__main__":
    main()
