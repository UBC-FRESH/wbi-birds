"""Maximum-bird endpoint solve (objective = bird abundance, even-flow on harvest).

Implements the manuscript's maximum bird abundance level: maximize bird
abundance in the objective function, subject to even-flow harvest volume
constraints. Writes the scenario CSV plus a per-period bird-series JSON
(consumed by ``campaign_partition.py --max-series``).

Usage:
    python scripts/campaign_birdmax.py --instance <built-instance> --unit TSA24 \
        [--species rebnut] [--harvest-expr "totvol * 0.85"] [--epsilon 0.1]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wbi_birds.bird import load_bird_response
from wbi_birds.model import build_model
from wbi_birds.results import write_scenario_result
from wbi_birds.runner import ProblemSpec, run_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, required=True, help="Built instance root.")
    parser.add_argument("--unit", required=True, help="Management-unit label (e.g. TSA24).")
    parser.add_argument("--species", default="rebnut", help="Bird species code (default: rebnut).")
    parser.add_argument(
        "--harvest-expr", default="totvol * 0.85", help="Harvest accounting/flow expression."
    )
    parser.add_argument("--epsilon", type=float, default=0.1, help="Even-flow epsilon.")
    parser.add_argument("--acode", default="cc", help="Harvest action code (default: cc).")
    parser.add_argument("--scenario-id", default=None, help="Scenario id (default: <unit>-bmax).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenario_id = args.scenario_id or f"{args.unit.lower()}-bmax"
    model, stats = build_model(args.instance)
    print("model stats:", stats)
    coefficients = load_bird_response(args.instance, args.species)
    spec = ProblemSpec(
        objective_expr="bird",
        flow_expr=args.harvest_expr,
        constraint_row="constraint",
        constraint_expr="bird",
        harvest_acodes=(args.acode,),
        acodes=("null", args.acode),
        measure_scope="landscape",
        bird_coefficients=coefficients,
        even_flow_epsilon=args.epsilon,
    )
    result = run_scenario(model, spec, scenario_id=scenario_id, management_unit=args.unit)
    print(
        f"{scenario_id} | {result.status} | harvest={result.harvest_volume_total_m3} "
        f"| birds={result.bird_abundance_total}"
    )
    if result.harvest_volume_total_m3 is not None:
        write_scenario_result(result, args.instance / "results")
        series_path = args.instance / "results" / f"{scenario_id}-series.json"
        series_path.write_text(json.dumps(list(result.bird_abundance_by_period)), encoding="utf-8")
        print("series:", series_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
