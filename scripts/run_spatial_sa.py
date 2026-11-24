"""Dual campaign driver (legacy direct entry; blocked outside FreshForge): aspatial vs spatial bird constraint on the resident SA.

Both modes share the same land base, target set, seed, and move machinery. In
``aspatial`` mode the bird floor is priced from the separable anticipation curves
held in ``BlockAccountState``; in ``spatial`` mode the same target is priced from
``SpatialBird20`` -- the exact period-20 spatial model -- while harvest and flow
still come from the resident state.

Formulation (the campaign convention, see ``sweep_epsilon.py``):
  * harvest: linear pull, minimum only (``--pull``), weight 1;
  * flow: even-flow band, non-linear, weight 1e4;
  * bird: period-20 floor, non-linear, weight 1e7.

Runs are chained: each epsilon is warm-started from the previous solution.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      python scripts/run_spatial_sa.py --dataset <compiled> --geometry <feather> \
        --fits <spatial-local json> --bird gockin \
        --epsilons 1.8e6 2.0e6 2.2e6 --iterations 2000000 --mode spatial --out out.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_model20 import SpatialBird20  # noqa: E402

BIRDS = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"
PERIOD_WIDTH = 10
YEAR = 199  # period-20 end offset

# Scenario runs are a FreshForge workflow. Direct invocation is allowed only for
# provider development, via WBI_ALLOW_DIRECT=1.
if not os.environ.get("FRESHFORGE_RUN_ID") and os.environ.get("WBI_ALLOW_DIRECT") != "1":
    raise SystemExit(
        "Direct scenario runs are disabled. Use "
        "`freshforge run workflows/ws4_evenflow_convergence.yaml`."
    )


def year_for(chain) -> float | None:
    """Return the last harvest year at or before period 20, or None."""
    if chain is None:
        return None
    last = None
    for _treatment, year in chain:
        if year <= YEAR and (last is None or year > last):
            last = int(year)
    return None if last is None else float(last)


def target_yaml(bird: str, epsilon: float, pull: float, band: float,
                include_flow: bool = True, flow_weight: float = 10000.0) -> str:
    lines = ["targets:"]
    for period in range(1, 21):
        lines += [
            f"- account: {HARVEST}",
            f"  period_width: {PERIOD_WIDTH}",
            f"  minimum: {pull:.1f}",
            "  min_weight: 1.0",
            "  shape: linear",
            f"  period: {period}",
        ]
    if include_flow:
        lines += [
            f"- account: {HARVEST}",
            "  period: 1",
            f"  period_width: {PERIOD_WIDTH}",
            "  flow: even",
            "  flow_start_period: 1",
            "  flow_end_period: 20",
            f"  minimum: {-band:.1f}",
            f"  maximum: {band:.1f}",
            f"  min_weight: {flow_weight:.1f}",
            f"  max_weight: {flow_weight:.1f}",
            "  shape: non_linear",
        ]
    lines += [
        f"- account: feature.Bird.{bird}",
        f"  period_width: {PERIOD_WIDTH}",
        f"  minimum: {epsilon:.1f}",
        "  min_weight: 10000000.0",
        "  shape: non_linear",
        "  period: 20",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, default=None)
    parser.add_argument("--fits", type=Path, default=None)
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--bird", default="gockin")
    parser.add_argument("--epsilons", nargs="+", type=float, required=True)
    parser.add_argument("--pull", type=float, default=40e6)
    parser.add_argument("--band", type=float, default=5.0)
    parser.add_argument("--iterations", type=int, default=2_000_000)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--stage1-iterations", type=int, default=200_000)
    parser.add_argument("--stage2-iterations", type=int, default=200_000)
    parser.add_argument("--flow-weight", type=float, default=10000.0)
    parser.add_argument("--fixed-initial", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mode", choices=("aspatial", "spatial"), required=True)
    parser.add_argument("--tsa", default=None)
    parser.add_argument("--initial", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--schedule-out", type=Path, default=None)
    args = parser.parse_args()

    if args.mode == "spatial" and (args.geometry is None or args.fits is None):
        parser.error("--geometry and --fits are required in spatial mode")

    from ws4.opt.engine import OptimizeConfig, Optimizer, load_schedule_csv
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory, run_state_sa
    from ws4.opt.objective import load_targets

    dataset = args.dataset
    tsa = args.tsa or dataset.name
    bird_account = f"feature.Bird.{args.bird}"
    accounts = (HARVEST, STOCK, bird_account)

    from ws4.opt.model2_index import CandidateIndex

    compact_path = dataset / "cache" / "candidates.npz"
    if args.candidates is None and compact_path.exists():
        index = CandidateIndex.load(compact_path)
        blocks = [int(b) for b in index.blocks]
        print(f"{tsa}: compact candidate index {len(blocks):,} blocks", flush=True)
    else:
        candidates_path = args.candidates or dataset / "cache" / "candidates.pkl"
        with candidates_path.open("rb") as stream:
            payload = pickle.load(stream)
        index = payload.get("candidates", payload) if isinstance(payload, dict) else payload
        blocks = sorted(int(b) for b in index if index.get(b))
    print(f"{tsa}: blocks with candidates {len(blocks):,}", flush=True)

    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(years=200, targets_path="/tmp/opencode/targets-level40.yaml", iterations=1, threads=1),
    )
    simulator = optimizer.simulator()
    # The bird target is a landscape total: the state must hold the unmanaged matrix even
    # though only blocks with candidates can be moved.
    state_blocks = sorted(int(b) for b in simulator.fragments["block_id"].unique())
    trajectory = TrackTrajectory.build(simulator, 200, accounts)

    spatial = None
    if args.mode == "spatial":
        from spatial_model20 import GUILDS
        if args.bird in GUILDS:
            spatial = SpatialBird20(dataset, args.geometry, args.fits, guild=args.bird)
        else:
            spatial = SpatialBird20(dataset, args.geometry, args.fits, species=args.bird)

    current = load_schedule_csv(args.initial) if args.initial is not None else {}
    rows: list[dict] = []

    def spatial_schedule(schedule: dict) -> dict[int, float]:
        return {int(b): year_for(c) for b, c in schedule.items() if year_for(c) is not None}

    kwargs = {}
    if spatial is not None:
        kwargs = {
            "spatial_model": spatial,
            "spatial_account": bird_account,
            "spatial_period": 19,
            "spatial_year": year_for,
        }

    for epsilon in args.epsilons:
        started = time.perf_counter()
        if args.staged:
            stage1_file = Path(f"/tmp/opencode/stage1-{tsa}-{args.mode}-{args.out.stem}-{epsilon:.0f}.yaml")
            stage1_file.parent.mkdir(parents=True, exist_ok=True)
            stage1_file.write_text(target_yaml(args.bird, epsilon, args.pull, args.band,
                                               include_flow=False, flow_weight=args.flow_weight))
            targets1 = load_targets(stage1_file)
            if spatial is not None:
                spatial.reset(spatial_schedule(current))
            state1 = BlockAccountState(
                trajectory, state_blocks, accounts, years=200, period_width=PERIOD_WIDTH, skip_empty=False
            )
            schedule1, _ = run_state_sa(
                state1, index, targets1, iterations=args.stage1_iterations,
                initial=current or None, seed=args.seed, **kwargs,
            )
            stage2_file = Path(f"/tmp/opencode/stage2-{tsa}-{args.mode}-{args.out.stem}-{epsilon:.0f}.yaml")
            stage2_file.write_text(target_yaml(args.bird, epsilon, args.pull, args.band,
                                               include_flow=True, flow_weight=args.flow_weight))
            targets = load_targets(stage2_file)
            if spatial is not None:
                spatial.reset(spatial_schedule(schedule1))
            state = BlockAccountState(
                trajectory, state_blocks, accounts, years=200, period_width=PERIOD_WIDTH, skip_empty=False
            )
            schedule, objective = run_state_sa(
                state, index, targets, iterations=args.stage2_iterations,
                initial=schedule1, seed=args.seed, **kwargs,
            )
            iterations_used = args.stage1_iterations + args.stage2_iterations
        else:
            targets_file = Path(f"/tmp/opencode/dual-target-{tsa}-{args.mode}-{args.out.stem}-{epsilon:.0f}.yaml")
            targets_file.parent.mkdir(parents=True, exist_ok=True)
            targets_file.write_text(target_yaml(args.bird, epsilon, args.pull, args.band,
                                                include_flow=True, flow_weight=args.flow_weight))
            targets = load_targets(targets_file)
            if spatial is not None:
                spatial.reset(spatial_schedule(current))
            state = BlockAccountState(
                trajectory, state_blocks, accounts, years=200, period_width=PERIOD_WIDTH, skip_empty=False
            )
            schedule, objective = run_state_sa(
                state, index, targets,
                iterations=args.iterations,
                initial=current or None,
                seed=args.seed,
                **kwargs,
            )
            iterations_used = args.iterations

        elapsed = time.perf_counter() - started

        harvest = state.period_totals[:, accounts.index(HARVEST)]
        stock = state.period_totals[:, accounts.index(STOCK)]
        if spatial is not None:
            spatial.reset(spatial_schedule(schedule))
            bird_p20 = float(spatial.totals()[args.bird])
        else:
            bird_p20 = float(state.period_totals[-1, accounts.index(bird_account)])

        row = {
            "tsa": tsa,
            "mode": args.mode,
            "bird": args.bird,
            "epsilon_p20": epsilon,
            "pull": args.pull,
            "band": args.band,
            "iterations": iterations_used,
            "staged": bool(args.staged),
            "seed": args.seed,
            "seconds": round(elapsed, 1),
            "objective": round(float(objective), 3),
            "harvest_mean_M": round(float(harvest.mean()) / 1e6, 3),
            "harvest_min_M": round(float(harvest.min()) / 1e6, 3),
            "harvest_max_M": round(float(harvest.max()) / 1e6, 3),
            "harvest_realized_m3_yr": round(float(harvest.mean()) / PERIOD_WIDTH / 1e6, 3),
            "stock_p20_M": round(float(stock[-1]) / 1e6, 1),
            "bird_p20": round(bird_p20, 1),
            "blocks_assigned": len(schedule),
        }
        rows.append(row)
        if args.schedule_out is not None:
            import pandas as pd
            pd.DataFrame(
                [{"block_id": b, "treatment": t, "offset": o}
                 for b, events in schedule.items() for t, o in events],
                columns=["block_id", "treatment", "offset"],
            ).to_csv(args.schedule_out, index=False)

        if not args.fixed_initial:
            current = schedule
        print(
            f"  {args.mode} eps {epsilon/1e6:.3f}M -> harvest {row['harvest_realized_m3_yr']:.3f} "
            f"M m3/yr, {args.bird} p20 {bird_p20/1e6:.3f} M, obj {row['objective']:.4g}, "
            f"{elapsed:.0f}s",
            flush=True,
        )

        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_header = not args.out.exists() or args.out.stat().st_size == 0
        with args.out.open("a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row))
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    print(f"wrote {len(rows)} rows to {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
