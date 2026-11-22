#!/usr/bin/env python
"""Verify ``BlockAccountState._period_rows`` against the retained reference.

``model2_trajectory.py`` keeps ``_period_rows_reference`` from before the speed
work.  This compares the two on random chains (no-event, single-event,
multi-event) and exits non-zero on any difference above ``--tolerance``.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/verify_state_rows.py --samples 400

The end-to-end exactness gate is separate and stronger: run ``ws4 state-watch``
with ``--summary-out``; it re-simulates the final schedule with
``IncrementalObjective`` and exits 1 when the objective disagrees.
"""

from __future__ import annotations

import argparse
import pickle
import random
import time
from pathlib import Path

import numpy as np

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
    parser.add_argument("--samples", type=int, default=400)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    parser.add_argument("--seed", type=int, default=23)
    args = parser.parse_args()

    dataset = args.dataset
    cache = dataset / "cache"

    from ws4.opt.engine import OptimizeConfig, Optimizer
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

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
    state.load_seed(cache / "seed-state.npz")
    blocks = [int(b) for b in state.blocks if index.get(int(b))]
    rng = random.Random(args.seed)

    worst = 0.0
    checked = 0
    for block in rng.sample(blocks, min(args.samples, len(blocks))):
        chains = index[block]
        pools = (
            [c for c in chains if not c],
            [c for c in chains if len(c) == 1],
            [c for c in chains if len(c) >= 2],
        )
        for pool in pools:
            if not pool:
                continue
            chain = rng.choice(pool)
            ref_state, ref_event = state._period_rows_reference(block, chain)
            new_state, new_event = state._period_rows(block, chain)
            worst = max(
                worst,
                float(np.max(np.abs(ref_state - new_state))),
                float(np.max(np.abs(ref_event - new_event))),
            )
            checked += 1
    print(f"checked {checked} rows  max_abs_diff={worst:.3e}", flush=True)
    if worst > args.tolerance:
        print("FAIL: vectorised rows differ from the reference", flush=True)
        return 1
    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
