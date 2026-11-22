"""Convert a candidate dict pickle to the compact CandidateIndex (.npz)."""
from __future__ import annotations
import argparse, pickle, time
from pathlib import Path
from ws4.opt.model2_index import CandidateIndex

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("datasets", nargs="+", type=Path)
    args = ap.parse_args()
    for dataset in args.datasets:
        src = dataset / "cache" / "candidates.pkl"
        dst = dataset / "cache" / "candidates.npz"
        started = time.perf_counter()
        with src.open("rb") as stream:
            payload = pickle.load(stream)
        candidates = payload.get("candidates", payload) if isinstance(payload, dict) else payload
        index = CandidateIndex.build(candidates)
        index.save(dst)
        print(f"{dataset.name}: {len(index.blocks):,} blocks, {len(index.event_years):,} events, "
              f"{dst.stat().st_size/1e6:.0f} MB, {time.perf_counter()-started:.0f}s", flush=True)
        del payload, candidates, index
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
