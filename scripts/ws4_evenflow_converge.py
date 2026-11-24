"""Run one ws4 even-flow harvest scenario through convergence.

Documented sequence:
  1. aspirational level pull, linear weight 1, no even-flow
  2. even-flow target, nonlinear high weight, level pull still active
  3. optional bird floor, nonlinear, from the converged even-flow schedule

Each stage runs in chunks and stops only when the best objective and realized
harvest have plateaued over a window. The trace, schedule and result record are
written; non-convergence is reported, not hidden.
"""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path("/srv/shared-data/gep/wbi-birds")
sys.path.insert(0, str(ROOT / "reference/wbi-main/scripts"))

HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"
PERIOD_WIDTH = 10


def target_text(aspirational, band, flow_weight, bird, epsilon, include_flow,
                level_shape='linear', level_weight=1.0):
    lines = ["targets:"]
    for period in range(1, 21):
        lines += [f"- account: {HARVEST}", f"  period_width: {PERIOD_WIDTH}",
                  f"  minimum: {aspirational:.1f}", f"  min_weight: {level_weight:.6g}",
                  f"  shape: {level_shape}", f"  period: {period}"]
    if include_flow:
        lines += [f"- account: {HARVEST}", "  period: 1", f"  period_width: {PERIOD_WIDTH}",
                  "  flow: even", "  flow_start_period: 1", "  flow_end_period: 20",
                  f"  minimum: {-band:.1f}", f"  maximum: {band:.1f}",
                  f"  min_weight: {flow_weight:.1f}", f"  max_weight: {flow_weight:.1f}",
                  "  shape: non_linear"]
    if bird is not None and epsilon is not None:
        lines += [f"- account: feature.Bird.{bird}", f"  period_width: {PERIOD_WIDTH}",
                  f"  minimum: {epsilon:.1f}", "  min_weight: 10000000.0",
                  "  shape: non_linear", "  period: 20"]
    return "\n".join(lines) + "\n"


def write_schedule(path, schedule):
    pd.DataFrame(
        [{"block_id": b, "treatment": t, "offset": o}
         for b, events in schedule.items() for t, o in events],
        columns=["block_id", "treatment", "offset"],
    ).to_csv(path, index=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--geometry", type=Path)
    ap.add_argument("--fits", type=Path)
    ap.add_argument("--mode", choices=("aspatial", "spatial"), required=True)
    ap.add_argument("--tsa", required=True)
    ap.add_argument("--bird", default=None)
    ap.add_argument("--epsilon", type=float, default=None)
    ap.add_argument("--aspirational", type=float, default=200_000_000.0)
    ap.add_argument("--band", type=float, default=1.0)
    ap.add_argument("--flow-weight", type=float, default=10000.0)
    ap.add_argument("--level-shape", choices=("linear", "non_linear"), default="linear")
    ap.add_argument("--level-weight", type=float, default=1.0)
    ap.add_argument("--no-evenflow", action="store_true")
    ap.add_argument("--chunk-iterations", type=int, default=50000)
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--tolerance", type=float, default=1e-4)
    ap.add_argument("--harvest-tolerance", type=float, default=1e-3)
    ap.add_argument("--max-iterations", type=int, default=2_000_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--initial", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    from ws4.opt.engine import OptimizeConfig, Optimizer, load_schedule_csv
    from ws4.opt.model2_index import CandidateIndex
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory, run_state_sa
    from ws4.opt.objective import load_targets
    from spatial_model20 import SpatialBird20, GUILDS

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "targets-level40.yaml").write_text(
        target_text(args.aspirational, args.band, args.flow_weight, None, None, False,
                    args.level_shape, args.level_weight))

    accounts = [HARVEST, STOCK]
    if args.bird:
        accounts.append(f"feature.Bird.{args.bird}")
    opt = Optimizer.from_dataset(
        args.dataset,
        OptimizeConfig(years=200, targets_path=str(args.out / "targets-level40.yaml"),
                       iterations=1, threads=1),
    )
    sim = opt.simulator()
    blocks = sorted(int(b) for b in sim.fragments["block_id"].unique())
    trajectory = TrackTrajectory.build(sim, 200, tuple(accounts))
    idx = {a: accounts.index(a) for a in accounts}

    compact = args.dataset / "cache" / "candidates.npz"
    if compact.exists():
        index = CandidateIndex.load(compact)
    else:
        with (args.dataset / "cache" / "candidates.pkl").open("rb") as stream:
            payload = pickle.load(stream)
        index = payload.get("candidates", payload) if isinstance(payload, dict) else payload

    spatial = None
    if args.mode == "spatial" and args.bird:
        spatial = (SpatialBird20(args.dataset, args.geometry, args.fits, guild=args.bird)
                   if args.bird in GUILDS else
                   SpatialBird20(args.dataset, args.geometry, args.fits, species=args.bird))

    def last_year(events):
        ys = [int(y) for _, y in events if int(y) <= 199]
        return float(max(ys)) if ys else None

    def sched_spatial(schedule):
        return {int(b): last_year(ev) for b, ev in schedule.items() if last_year(ev) is not None}

    initial = load_schedule_csv(args.initial) if args.initial else {}
    stages = []

    def stage(name, include_flow, use_bird, start):
        target = args.out / f"target-{name}.yaml"
        target.write_text(target_text(args.aspirational, args.band, args.flow_weight,
                                      args.bird if use_bird else None,
                                      args.epsilon if use_bird else None, include_flow,
                                      args.level_shape, args.level_weight))
        targets = load_targets(target)
        kwargs = {}
        if spatial is not None and use_bird:
            kwargs = {"spatial_model": spatial,
                      "spatial_account": f"feature.Bird.{args.bird}",
                      "spatial_period": 19, "spatial_year": last_year}
        current = dict(start)
        best = float("inf")
        hist = []
        converged = False
        total = 0
        trace_path = args.out / f"trace-{name}.jsonl"
        while total < args.max_iterations:
            if spatial is not None and use_bird:
                spatial.reset(sched_spatial(current))
            state = BlockAccountState(trajectory, blocks, tuple(accounts), years=200,
                                      period_width=PERIOD_WIDTH, skip_empty=False)
            schedule, objective = run_state_sa(
                state, index, targets, iterations=args.chunk_iterations,
                initial=current or None, seed=args.seed, **kwargs,
            )
            total += args.chunk_iterations
            harvest = float(state.period_totals[:, idx[HARVEST]].mean()) / PERIOD_WIDTH / 1e6
            bird_val = None
            if use_bird:
                if spatial is not None:
                    spatial.reset(sched_spatial(schedule))
                    bird_val = float(spatial.totals()[args.bird])
                else:
                    bird_val = float(state.period_totals[-1, idx[f"feature.Bird.{args.bird}"]])
            best = min(best, float(objective))
            hist.append({"iterations": total, "objective": float(objective), "best": best,
                         "harvest": harvest, "bird": bird_val})
            with trace_path.open("a") as handle:
                handle.write(json.dumps(hist[-1]) + "\n")
            current = schedule
            if len(hist) >= args.window:
                recent = hist[-args.window:]
                obj_rel = (recent[0]["best"] - best) / max(abs(recent[0]["best"]), 1e-12)
                hs = [row["harvest"] for row in recent]
                h_rel = (max(hs) - min(hs)) / max(sum(hs) / len(hs), 1e-12)
                if obj_rel < args.tolerance and h_rel < args.harvest_tolerance:
                    converged = True
                    break
        write_schedule(args.out / f"schedule-{name}.csv", current)
        stage_rec = {"stage": name, "converged": converged, "iterations": total,
                     "objective": float(objective), "harvest": harvest,
                     "bird": bird_val, "trace": str(trace_path),
                     "schedule": str(args.out / f"schedule-{name}.csv")}
        stages.append(stage_rec)
        print(json.dumps(stage_rec), flush=True)
        return current, converged, stage_rec

    s1, ok1, rec1 = stage("level", False, False, initial)
    if args.no_evenflow:
        ok2, ok3, last, final_schedule = True, True, rec1, "schedule-level.csv"
    else:
        s2, ok2, rec2 = stage("evenflow", True, False, s1)
        if args.bird:
            _s3, ok3, rec3 = stage("bird", True, True, s2)
            last, final_schedule = rec3, "schedule-bird.csv"
        else:
            ok3, last, final_schedule = True, rec2, "schedule-evenflow.csv"
    result = {
        "tsa": args.tsa, "mode": args.mode, "bird": args.bird, "epsilon": args.epsilon,
        "converged": bool(ok1 and ok2 and ok3),
        "stages": stages,
        "harvest_M_m3_yr": last.get("harvest"),
        "bird_p20": last.get("bird"),
        "schedule": str(args.out / final_schedule),
        "aspirational": args.aspirational, "band": args.band, "flow_weight": args.flow_weight,
        "chunk_iterations": args.chunk_iterations, "window": args.window,
        "tolerance": args.tolerance, "harvest_tolerance": args.harvest_tolerance,
        "max_iterations": args.max_iterations, "seed": args.seed,
    }
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"result": str(args.out / "result.json"), "converged": result["converged"]}), flush=True)
    return 0 if result["converged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
