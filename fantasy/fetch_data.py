"""Download free NFL + fantasy data. No API keys, no scraping, no auth.

Everything here is published as plain files on GitHub by two open-data projects:

  nflverse (github.com/nflverse)          — official play-by-play, weekly player
                                            stats, snap counts, rosters, injuries
  DynastyProcess (github.com/dynastyprocess) — weekly FantasyPros expert consensus
                                            rankings + a cross-platform player ID
                                            map that includes Yahoo IDs

    python3 fetch_data.py            # everything
    python3 fetch_data.py rankings   # just the rankings (fast, do this pre-draft)
"""

from __future__ import annotations

import os
import sys
import urllib.request

from engine import HERE

RAW = os.path.join(HERE, "data", "raw")

NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
DP = "https://raw.githubusercontent.com/dynastyprocess/data/master/files"

# Seasons of actual results used to calibrate the rank -> points curve.
SEASONS = (2023, 2024, 2025)

SOURCES: dict[str, list[tuple[str, str]]] = {
    "rankings": [
        (f"{DP}/db_fpecr_latest.csv", "fp_ecr.csv"),
        (f"{DP}/db_playerids.csv", "player_ids.csv"),
    ],
    "stats": [
        (f"{NFLVERSE}/stats_player/stats_player_week_{y}.csv", f"stats_{y}.csv")
        for y in SEASONS
    ],
    "usage": [
        (f"{NFLVERSE}/snap_counts/snap_counts_2025.csv", "snap_counts_2025.csv"),
        (
            "https://github.com/ffverse/ffopportunity/releases/download/"
            "latest-data/ep_weekly_2025.csv",
            "expected_points_2025.csv",
        ),
    ],
    "schedule": [
        ("https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
         "schedule_2026.csv"),
    ],
    "context": [
        (f"{NFLVERSE}/injuries/injuries_2025.csv", "injuries_2025.csv"),
        (f"{NFLVERSE}/rosters/roster_2025.csv", "roster_2025.csv"),
    ],
}


def download(url: str, dest: str) -> bool:
    path = os.path.join(RAW, dest)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ff-toolkit"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(path, "wb") as fh:
            fh.write(resp.read())
    except Exception as exc:  # noqa: BLE001 - report and continue to next file
        print(f"  FAIL  {dest:<28} {type(exc).__name__}: {exc}")
        return False
    print(f"  ok    {dest:<28} {os.path.getsize(path) / 1e6:>7.1f} MB")
    return True


def main(groups: list[str]) -> int:
    os.makedirs(RAW, exist_ok=True)
    failed = 0
    for group in groups:
        if group not in SOURCES:
            print(f"unknown group '{group}' (have: {', '.join(SOURCES)})")
            return 2
        print(f"\n{group}:")
        for url, dest in SOURCES[group]:
            if not download(url, dest):
                failed += 1
    print(f"\n-> {RAW}")
    if failed:
        print(f"{failed} file(s) failed — a source may have renamed an asset.")
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:] or list(SOURCES)
    sys.exit(main(args))
