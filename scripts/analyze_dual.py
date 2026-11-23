"""Apply the pre-registered parsimony rule to the dual-campaign grid.

Points are matched on the **constraint target** (epsilon / no-harvest baseline), not on the
realized abundance, because realized values differ slightly between seeds and modes.
For each (TSA, species, target) the best objective per mode is kept.

    python scripts/analyze_dual.py --csv dual/tsa*-multi-s*.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def read_rows(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", nargs="+", type=Path, required=True)
    parser.add_argument("--rule", type=float, default=2.0, help="percent harvest tolerance")
    parser.add_argument("--feasible-only", action="store_true",
                        help="keep only pairs where both modes meet the floor")
    parser.add_argument("--deficit-tolerance", type=float, default=0.002,
                        help="relative deficit allowed when calling a point feasible")
    parser.add_argument("--pairs-out", type=Path, default=None)
    args = parser.parse_args()

    best: dict[tuple, dict] = {}
    baseline_cache: dict[str, dict] = {}
    for path in args.csv:
        rows = read_rows(path)
        if not rows or "tsa" not in rows[0]:
            continue
        tsa = rows[0]["tsa"]
        if tsa not in baseline_cache:
            baseline_path = path.parent / f"{tsa}-baselines.json"
            if not baseline_path.exists():
                print(f"missing baselines for {tsa}: {baseline_path}")
                return 1
            baseline_cache[tsa] = json.loads(baseline_path.read_text())
        baseline = baseline_cache[tsa]
        for row in rows:
            bird, mode = row["bird"], row["mode"]
            target = round(float(row["epsilon_p20"]) / float(baseline[mode][bird]), 3)
            key = (tsa, bird, target, mode)
            objective = float(row["objective"])
            if key not in best or objective < float(best[key]["objective"]):
                best[key] = row

    pairs: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for (tsa, bird, target, mode), row in best.items():
        pairs[(tsa, bird, target)][mode] = row

    print(f"{'tsa':6s} {'bird':8s} {'target':>6s} {'asp':>7s} {'sp':>7s} {'delta%':>8s} "
          f"{'asp deficit':>11s} {'sp deficit':>10s}")
    deltas: list[float] = []
    pair_rows: list[dict] = []
    for (tsa, bird, target), modes in sorted(pairs.items()):
        if "aspatial" not in modes or "spatial" not in modes:
            continue
        a, s = modes["aspatial"], modes["spatial"]
        da = float(a["epsilon_p20"]) - float(a["bird_p20"])
        ds = float(s["epsilon_p20"]) - float(s["bird_p20"])
        if args.feasible_only:
            tol_a = args.deficit_tolerance * float(a["epsilon_p20"])
            tol_s = args.deficit_tolerance * float(s["epsilon_p20"])
            if da > tol_a or ds > tol_s:
                continue
        ha, hs = float(a["harvest_realized_m3_yr"]), float(s["harvest_realized_m3_yr"])
        delta = 100.0 * (ha - hs) / hs if hs else float("inf")
        deltas.append(abs(delta))
        pair_rows.append(dict(tsa=tsa, bird=bird, target=target, aspatial=ha, spatial=hs,
                              delta_pct=delta, aspatial_deficit=da, spatial_deficit=ds))
        print(f"{tsa:6s} {bird:8s} {target:6.2f} {ha:7.3f} {hs:7.3f} {delta:8.1f} "
              f"{da:11.0f} {ds:10.0f}")

    if args.pairs_out is not None:
        import pandas as pd
        args.pairs_out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(pair_rows).to_csv(args.pairs_out, index=False)
    if not deltas:
        print("no matched pairs")
        return 0
    worst = max(deltas)
    median = statistics.median(deltas)
    print()
    print(f"matched points: {len(deltas)}; median |delta harvest| {median:.1f}%; worst {worst:.1f}%")
    print("aspatial PREFERRED" if worst <= args.rule else "aspatial REJECTED for this comparison")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
