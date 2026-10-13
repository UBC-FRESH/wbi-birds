"""Eleven-scenario bird partition from nadir to maximum (manuscript Methods).

Per-period bird floors interpolate linearly between the nadir (max-harvest
baseline) series and the maximum-bird series (from ``campaign_birdmax.py``, or
approximated by bisection on a flat multiple of the nadir series when
``--max-series`` is not given). Period 1 is exempt (fixed by initial
inventory). Scenario CSVs are written as ``<unit>-cbird<0.00..1.00>.csv``.

Usage:
    python scripts/campaign_partition.py --instance <built-instance> --unit TSA24 \
        --baseline <results/scenarios/tsa24/tsa24-f100.csv> \
        [--max-series <bmax-series.json>] [--lo 1.05 --hi 1.08]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from wbi_birds.bird import load_bird_response
from wbi_birds.model import build_model
from wbi_birds.results import write_scenario_result
from wbi_birds.runner import ProblemSpec, run_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--baseline", type=Path, required=True, help="Nadir scenario CSV.")
    parser.add_argument("--max-series", type=Path, default=None, help="Max-bird series JSON.")
    parser.add_argument("--lo", type=float, default=1.05, help="Bisection lower factor.")
    parser.add_argument("--hi", type=float, default=1.60, help="Bisection upper factor.")
    parser.add_argument("--scenarios", type=int, default=11)
    parser.add_argument("--species", default="rebnut")
    parser.add_argument("--harvest-expr", default="totvol * 0.85")
    parser.add_argument("--epsilon", type=float, default=0.1)
    parser.add_argument("--acode", default="cc")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model, stats = build_model(args.instance)
    print("model stats:", stats, flush=True)
    coefficients = load_bird_response(args.instance, args.species)

    def make_spec() -> ProblemSpec:
        return ProblemSpec(
            objective_expr=args.harvest_expr,
            constraint_row="constraint",
            constraint_expr="bird",
            harvest_acodes=(args.acode,),
            acodes=("null", args.acode),
            measure_scope="landscape",
            bird_coefficients=coefficients,
            even_flow_epsilon=args.epsilon,
        )

    def attempt(floors, scenario_id):
        try:
            return run_scenario(
                model,
                make_spec(),
                scenario_id=scenario_id,
                management_unit=args.unit,
                constraint_floor=floors,
            )
        except Exception:
            return None

    nadir_series = list(pd.read_csv(args.baseline)["bird_abundance"])
    if args.max_series:
        max_series = json.loads(args.max_series.read_text())
        print(f"using supplied max series ({len(max_series)} periods)", flush=True)
    else:
        lo, hi, best = args.lo, args.hi, None
        for _ in range(8):
            mid = (lo + hi) / 2.0
            result = attempt(
                {p: mid * v for p, v in enumerate(nadir_series, start=1) if p >= 2},
                f"{args.unit.lower()}-bisect-{mid:.3f}",
            )
            feasible = result is not None and result.harvest_volume_total_m3 is not None
            print(f"bisect {mid:.3f} -> {'feasible' if feasible else 'infeasible'}", flush=True)
            if feasible:
                lo, best = mid, result
            else:
                hi = mid
            if hi - lo < 0.005:
                break
        if best is None:
            print(f"ERROR: no feasible factor in [{args.lo}, {args.hi}]", file=sys.stderr)
            return 1
        max_series = list(best.bird_abundance_by_period)
        write_scenario_result(best, args.instance / "results")

    summary = []
    for i in range(args.scenarios):
        weight = i / (args.scenarios - 1)
        scenario_id = f"{args.unit.lower()}-cbird{weight:.2f}"
        if i == 0:
            result = run_scenario(
                model, make_spec(), scenario_id=scenario_id, management_unit=args.unit
            )
        else:
            floors = {
                p: nadir + weight * (mx - nadir)
                for p, (nadir, mx) in enumerate(zip(nadir_series, max_series, strict=True), start=1)
                if p >= 2
            }
            result = attempt(floors, scenario_id)
        if result is None or result.harvest_volume_total_m3 is None:
            print(f"{scenario_id} | infeasible", flush=True)
            continue
        write_scenario_result(result, args.instance / "results")
        summary.append(
            {
                "scenario": scenario_id,
                "harvest_m3": result.harvest_volume_total_m3,
                "birds": result.bird_abundance_total,
            }
        )
        print(
            f"{scenario_id} | {result.status:<9} | {result.harvest_volume_total_m3:>15,.0f} "
            f"| {result.bird_abundance_total:>13,.0f}",
            flush=True,
        )
    out = args.instance / "results" / f"{args.unit.lower()}-partition.json"
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("partition summary:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
