"""Summarize a set of scenario CSVs as a harvest/bird trade-off table.

Usage:
    python scripts/frontier_analyze.py --scenario-dir <instance>/results/scenarios/tsa24 \
        [--glob "tsa24-cbird*.csv"]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-dir", type=Path, required=True)
    parser.add_argument("--glob", default="*.csv", help="Scenario file glob.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = sorted(args.scenario_dir.glob(args.glob))
    if not paths:
        print("no scenarios matched")
        return 1
    base_harvest = base_birds = None
    print("scenario | harvest (m3) | birds | dHarvest | dBirds")
    for path in paths:
        frame = pd.read_csv(path)
        harvest = frame["harvest_volume_m3"].sum()
        birds = frame["bird_abundance"].sum()
        if base_harvest is None:
            base_harvest, base_birds = harvest, birds
        dh = (harvest / base_harvest - 1.0) * 100 if base_harvest else 0.0
        db = (birds / base_birds - 1.0) * 100 if base_birds else 0.0
        print(f"{path.stem} | {harvest:,.0f} | {birds:,.0f} | {dh:+.1f}% | {db:+.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
