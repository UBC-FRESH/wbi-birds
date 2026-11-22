"""One-call dual campaign for a TSA/species pair.

Computes each model's own no-harvest period-20 baseline, converts the requested
attainments into per-mode epsilons, then runs both modes with the established
driver (``run_spatial_sa.py``).  Baselines are cached per TSA.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      python scripts/dual_campaign.py --dataset <compiled> --geometry <feather> \
        --fits <spatial-local> --tsa tsa41 --bird gockin \
        --attainments 0.85 0.90 0.95 --iterations 300000 \
        --prime campaigns/.../prime/tsa41-prime.csv --out campaigns/.../dual/tsa41-gockin.csv
"""
from __future__ import annotations

import argparse
import json
import pickle
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_model20 import SpatialBird20  # noqa: E402

HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"


def no_harvest_baselines(dataset: Path, geometry: Path, fits: Path, birds: tuple[str, ...]) -> dict:
    """Return aspatial and spatial period-20 abundance with no harvest."""
    from ws4.opt.engine import OptimizeConfig, Optimizer
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

    accounts = (HARVEST, STOCK, *[f"feature.Bird.{b}" for b in birds])
    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(years=200, targets_path="/tmp/opencode/targets-level40.yaml", iterations=1, threads=1),
    )
    simulator = optimizer.simulator()
    blocks = sorted(int(b) for b in simulator.fragments["block_id"].unique())
    trajectory = TrackTrajectory.build(simulator, 200, accounts)
    state = BlockAccountState(trajectory, blocks, accounts, years=200, period_width=10, skip_empty=False)

    out = {"aspatial": {}, "spatial": {}}
    for bird in birds:
        out["aspatial"][bird] = float(state.period_totals[-1, accounts.index(f"feature.Bird.{bird}")])
        model = SpatialBird20(dataset, geometry, fits, species=bird)
        out["spatial"][bird] = float(model.totals()[bird])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--fits", type=Path, required=True)
    parser.add_argument("--tsa", required=True)
    parser.add_argument("--bird", nargs="+", required=True)
    parser.add_argument("--attainments", nargs="+", type=float, default=[0.85, 0.90, 0.95])
    parser.add_argument("--iterations", type=int, default=300_000)
    parser.add_argument("--pull", type=float, default=40e6)
    parser.add_argument("--band", type=float, default=5.0)
    parser.add_argument("--prime", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--driver", type=Path, default=Path(__file__).with_name("run_spatial_sa.py"))
    args = parser.parse_args()

    cache_path = args.out.with_name(f"{args.tsa}-baselines.json")
    baseline = json.loads(cache_path.read_text()) if cache_path.exists() else {"aspatial": {}, "spatial": {}}
    missing = [b for b in args.bird if b not in baseline["aspatial"] or b not in baseline["spatial"]]
    if missing:
        baseline.update(no_harvest_baselines(args.dataset, args.geometry, args.fits, tuple(missing)))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(baseline, indent=2) + "\n")
    print(json.dumps({k: {b: round(baseline[k][b]) for b in args.bird} for k in baseline}, indent=2))

    order = sorted(args.attainments, reverse=True)  # most constrained first
    for bird in args.bird:
        eps_aspatial = [round(a * baseline["aspatial"][bird]) for a in order]
        eps_spatial = [round(a * baseline["spatial"][bird]) for a in order]
        common = [
            "--dataset", str(args.dataset), "--bird", bird, "--iterations", str(args.iterations),
            "--pull", str(args.pull), "--band", str(args.band), "--tsa", args.tsa,
            "--initial", str(args.prime), "--out", str(args.out), "--seed", str(args.seed),
        ]
        def sched_out(mode: str) -> str:
            return str(args.out.with_name(f"{args.out.stem}-{bird}-{mode}-schedules.csv"))
        print(f"=== {bird} aspatial eps {eps_aspatial}", flush=True)
        subprocess.run([sys.executable, str(args.driver), *common,
                        "--epsilons", *map(str, eps_aspatial), "--mode", "aspatial",
                        "--schedule-out", sched_out("aspatial")], check=True)
        print(f"=== {bird} spatial eps {eps_spatial}", flush=True)
        subprocess.run([sys.executable, str(args.driver), *common,
                        "--geometry", str(args.geometry), "--fits", str(args.fits),
                        "--epsilons", *map(str, eps_spatial), "--mode", "spatial",
                        "--schedule-out", sched_out("spatial")], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
