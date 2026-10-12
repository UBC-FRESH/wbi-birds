"""Even-flow epsilon and utilization sensitivity at matched bird targets.

Bird floors are absolute values derived from a baseline series (matched targets
across settings). Utilization runs use ``--eps`` omitted (no even-flow) unless
given.

Usage:
    python scripts/campaign_sensitivity.py --instance <built-instance> --unit TSA24 \
        --baseline <nadir.csv> --eps 0.05 --factors 1.02,1.05
    python scripts/campaign_sensitivity.py --instance <built-instance> --unit TSA24 \
        --baseline <nadir.csv> --util 0.90 --factors 1.00,1.05
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from wbi_birds.bird import load_coefficients
from wbi_birds.model import build_model
from wbi_birds.results import write_scenario_result
from wbi_birds.runner import ProblemSpec, run_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline series CSV.")
    parser.add_argument("--eps", type=float, default=None, help="Even-flow epsilon (None = off).")
    parser.add_argument("--util", type=float, default=0.85, help="Utilization factor.")
    parser.add_argument("--factors", default="1.00", help="Comma-separated floor factors.")
    parser.add_argument("--species", default="rebnut")
    parser.add_argument("--acode", default="cc")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model, stats = build_model(args.instance)
    print("model stats:", stats, flush=True)
    coefficients = load_coefficients(args.instance, args.species)
    baseline_series = list(pd.read_csv(args.baseline)["bird_abundance"])
    tag = f"eps{args.eps:g}" if args.eps is not None else f"util{args.util:g}"
    print(f"tag={tag} eps={args.eps} util={args.util} factors={args.factors}", flush=True)
    for factor in (float(f) for f in args.factors.split(",")):
        scenario_id = f"{args.unit.lower()}-{tag}-f{round(factor * 100):03d}"
        floors = None
        if factor != 1.0:
            floors = {p: factor * v for p, v in enumerate(baseline_series, start=1) if p >= 2}
        spec = ProblemSpec(
            objective_expr=f"totvol * {args.util}",
            constraint_row="constraint",
            constraint_expr="bird",
            harvest_acodes=(args.acode,),
            acodes=("null", args.acode),
            measure_scope="landscape",
            bird_coefficients=coefficients,
            even_flow_epsilon=args.eps,
        )
        try:
            result = run_scenario(
                model,
                spec,
                scenario_id=scenario_id,
                management_unit=args.unit,
                constraint_floor=floors,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"{scenario_id} | EXCEPTION | {type(exc).__name__}: {exc}", flush=True)
            continue
        print(
            f"{scenario_id} | {result.status:<9} | {result.harvest_volume_total_m3} "
            f"| {result.bird_abundance_total}",
            flush=True,
        )
        if result.harvest_volume_total_m3 is not None:
            write_scenario_result(result, args.instance / "results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
