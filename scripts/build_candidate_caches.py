#!/usr/bin/env python
"""Build simulator + candidate caches for one or more compiled datasets.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/build_candidate_caches.py <dataset> [<dataset> ...]

Uses the engine's current candidate caps.  Prints blocks, chains, chains/block,
wall time, and peak RSS after each dataset.
"""
from __future__ import annotations

import resource
import sys
import time
from pathlib import Path


def build(dataset: Path) -> None:
    from ws4.opt.candidate_cache import load_or_build_candidates, load_or_build_simulator
    from ws4.opt.engine import OptimizeConfig, Optimizer

    cache = dataset / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(
            years=200,
            targets_path=str(dataset / "targets-evenflow-steady-v7.yaml"),
            iterations=1,
            threads=1,
        ),
    )
    load_or_build_simulator(optimizer, cache / "simulator.pkl")
    candidates = load_or_build_candidates(optimizer, cache / "candidates.pkl")
    elapsed = time.perf_counter() - started
    chains = sum(len(value) for value in candidates.values())
    blocks = sum(1 for value in candidates.values() if value)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    size = (cache / "candidates.pkl").stat().st_size / 1e9
    print(
        f"{dataset.name}: blocks={blocks:,} chains={chains:,} "
        f"per_block={chains / max(blocks, 1):.1f} pickle={size:.2f}GB "
        f"sec={elapsed:.0f} peak_rss={peak:.0f}MB",
        flush=True,
    )


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for argument in sys.argv[1:]:
        build(Path(argument))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
