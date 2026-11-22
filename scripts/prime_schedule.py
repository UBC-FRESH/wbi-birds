"""Build a prime schedule for a compiled dataset (cold start needs two stages).

Stage 1: level pull only (no even-flow).  A zero-harvest cold start makes the
even-flow target divide by a zero reference, so flow is switched on only once a
harvest profile exists.

Stage 2: level pull + even-flow band, warm-started from stage 1.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/prime_schedule.py --dataset <compiled-bird> \
      --iterations 300000 --out <prime.csv>
"""
from __future__ import annotations

import argparse
import pickle
import time
from pathlib import Path

import pandas as pd

HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"
ACCOUNTS = (HARVEST, STOCK)


def level_yaml(pull: float, band: float | None, band_weight: float = 1e9) -> str:
    lines = ["targets:"]
    for period in range(1, 21):
        lines += [
            f"- account: {HARVEST}",
            "  period_width: 10",
            f"  minimum: {pull:.1f}",
            "  min_weight: 1.0",
            "  shape: linear",
            f"  period: {period}",
        ]
    if band is not None:
        lines += [
            f"- account: {HARVEST}",
            "  period: 1",
            "  period_width: 10",
            "  flow: even",
            "  flow_start_period: 1",
            "  flow_end_period: 20",
                        f"  minimum: {-band:.1f}",
            f"  maximum: {band:.1f}",
            f"  min_weight: {band_weight:.1f}",
            f"  max_weight: {band_weight:.1f}",
            "  shape: non_linear",
        ]
    return "\n".join(lines) + "\n"


def write_schedule(schedule: dict, path: Path) -> None:
    rows = [
        {"block_id": b, "treatment": t, "offset": o}
        for b, events in schedule.items()
        for t, o in events
    ]
    pd.DataFrame(rows, columns=["block_id", "treatment", "offset"]).to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=300000)
    parser.add_argument("--pull", type=float, default=40e6)
    parser.add_argument("--band", type=float, default=10.0)
    parser.add_argument("--band-weight", type=float, default=1e9)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from ws4.opt.engine import OptimizeConfig, Optimizer
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory, run_state_sa
    from ws4.opt.objective import load_targets

    dataset = args.dataset
    with (dataset / "cache" / "candidates.pkl").open("rb") as stream:
        payload = pickle.load(stream)
    index = payload.get("candidates", payload) if isinstance(payload, dict) else payload
    blocks = sorted(int(b) for b in index if index.get(b))
    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(
            years=200,
            targets_path=str(dataset / "targets-evenflow-steady-v7.yaml"),
            iterations=1,
            threads=1,
        ),
    )
    trajectory = TrackTrajectory.build(optimizer.simulator(), 200, ACCOUNTS)

    import os

    stage_file = Path(f"/tmp/opencode/prime-stage-{dataset.name}-{os.getpid()}.yaml")
    schedule = None
    for stage, band in ((1, None), (2, args.band)):
        stage_file.write_text(level_yaml(args.pull, band, args.band_weight))
        targets = load_targets(stage_file)
        started = time.perf_counter()
        state = BlockAccountState(
            trajectory, blocks, ACCOUNTS, years=200, period_width=10, skip_empty=False
        )
        schedule, objective = run_state_sa(
            state, index, targets, iterations=args.iterations, initial=schedule, seed=args.seed
        )
        harvest = state.period_totals[:, 0]
        print(
            f"stage {stage} band={band} -> harvest {harvest.mean()/10/1e6:.3f} M/yr "
            f"min {harvest.min()/1e6:.2f} max {harvest.max()/1e6:.2f} "
            f"obj {objective:.3g} ({time.perf_counter()-started:.0f}s)",
            flush=True,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_schedule(schedule, args.out)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
