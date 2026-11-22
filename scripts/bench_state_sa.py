#!/usr/bin/env python
"""Benchmark the resident state SA loop (``ws4 state-watch`` core).

Loads the TSA41 compiled dataset, applies the seed state, and times
``run_state_sa`` with no rendering, so the reported rate is the engine rate.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/bench_state_sa.py --iterations 50000

Set ``WS4_PHASE_TIMING=1`` to print the per-phase split (move / rows / value)
from the env-guarded timers in ``model2_trajectory.run_state_sa``.

Measurement hazards (both cost real time if ignored):
  * cProfile inflates tiny functions ~100x here; do not rank costs from it.
  * the first ``set_block`` builds the 148k-entry block index (several seconds);
    always warm up before timing or the average is meaningless.
"""

from __future__ import annotations

import argparse
import pickle
import time
from pathlib import Path

DEFAULT_DATASET = Path(
    "/srv/shared-data/gep/ws4/femic/external/femic-tsa41-instance/output"
    "/patchworks_tsa41_p120/compiled-bird"
)
ACCOUNTS = (
    "product.HarvestedVolume.managed.Total.CC",
    "feature.Yield.managed.Total",
    "feature.Bird.rebnut",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--targets", type=Path, default=None)
    parser.add_argument("--warmup", type=int, default=500)
    parser.add_argument("--iterations", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    dataset = args.dataset
    targets_path = args.targets or dataset / "targets-evenflow-steady-v7.yaml"
    cache = dataset / "cache"

    from ws4.opt.engine import OptimizeConfig, Optimizer, load_schedule_csv
    from ws4.opt.model2_trajectory import (
        BlockAccountState,
        TrackTrajectory,
        run_state_sa,
    )
    from ws4.opt.objective import load_targets

    started = time.perf_counter()
    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(
            years=200, targets_path=str(targets_path), iterations=1, threads=1
        ),
    )
    targets = load_targets(targets_path)
    trajectory = TrackTrajectory.build(optimizer.simulator(), 200, ACCOUNTS)
    state = BlockAccountState(
        trajectory,
        sorted(int(b) for b in optimizer.simulator().fragments["block_id"].unique()),
        ACCOUNTS,
        years=200,
        period_width=10,
        skip_empty=True,
    )
    with cache.joinpath("candidates.pkl").open("rb") as stream:
        payload = pickle.load(stream)
    index = payload.get("candidates", payload) if isinstance(payload, dict) else payload
    initial = load_schedule_csv(dataset / "run-level-prime-minage" / "schedule.csv")
    state.load_seed(cache / "seed-state.npz")
    print(f"setup {time.perf_counter() - started:.1f}s", flush=True)

    if args.warmup:
        run_state_sa(
            state, index, targets, iterations=args.warmup, initial=initial, seed=args.seed
        )

    started = time.perf_counter()
    schedule, objective = run_state_sa(
        state, index, targets, iterations=args.iterations, initial=initial, seed=args.seed
    )
    elapsed = time.perf_counter() - started
    print(
        f"{args.iterations} iters in {elapsed:.2f}s  "
        f"{elapsed / args.iterations * 1000:.3f} ms/iter  "
        f"{args.iterations / elapsed:.1f} eval/s  "
        f"objective {objective:.6g}  blocks {len(schedule)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
