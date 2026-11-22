"""Build a fine harvest-attainment frontier for one guild and TSA.

Computes each model's no-harvest guild abundance, then runs one e-constraint point per
attainment for both anticipation models in parallel (one process each).

    PYTHONPATH=... python scripts/guild_frontier.py \
      --dataset campaigns/.../full-landscape/tsa41 \
      --geometry /tmp/opencode/rebuild/tsa41/data/vri_vclr1p_checkpoint7.feather \
      --fits campaigns/.../bird-fits/knn-v0-nine-species-spatial-local.json \
      --guild mature_conifer --tsa tsa41 \
      --attainments 0.70 1.00 0.02 --iterations 300000 --workers 32 \
      --out campaigns/.../dual/tsa41-mature_conifer-frontier.csv
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--fits", type=Path, required=True)
    parser.add_argument("--guild", required=True)
    parser.add_argument("--tsa", required=True)
    parser.add_argument("--attainments", nargs=3, type=float, default=[0.70, 1.00, 0.02],
                        metavar=("START", "STOP", "STEP"))
    parser.add_argument("--iterations", type=int, default=300_000)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--driver", type=Path, default=Path(__file__).with_name("run_spatial_sa.py"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from spatial_model20 import SpatialBird20
    from ws4.opt.engine import OptimizeConfig, Optimizer

    account = f"feature.Bird.{args.guild}"
    optimizer = Optimizer.from_dataset(
        args.dataset, OptimizeConfig(years=200, targets_path="/tmp/opencode/targets-level40.yaml",
                                     iterations=1, threads=1))
    simulator = optimizer.simulator()
    blocks = sorted(int(b) for b in simulator.fragments["block_id"].unique())
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

    trajectory = TrackTrajectory.build(simulator, 200, (HARVEST, STOCK, account))
    state = BlockAccountState(trajectory, blocks, (HARVEST, STOCK, account),
                              years=200, period_width=10, skip_empty=False)
    base_aspatial = float(state.period_totals[-1, 2])
    model = SpatialBird20(args.dataset, args.geometry, args.fits, guild=args.guild)
    base_spatial = float(model.totals()[args.guild])
    print(f"baselines: aspatial {base_aspatial:,.0f}  spatial {base_spatial:,.0f}", flush=True)

    start, stop, step = args.attainments
    attainments = []
    x = start
    while x <= stop + 1e-9:
        attainments.append(round(x, 3)); x += step

    jobs = []
    work = Path("/tmp/opencode/guild-frontier")
    work.mkdir(parents=True, exist_ok=True)
    for att in attainments:
        for mode, baseline in (("aspatial", base_aspatial), ("spatial", base_spatial)):
            epsilon = round(att * baseline)
            out = work / f"{mode}-{int(epsilon)}.csv"
            if not args.reuse:
                out.unlink(missing_ok=True)
            command = [sys.executable, str(args.driver),
                       "--dataset", str(args.dataset), "--bird", args.guild,
                       "--epsilons", str(epsilon), "--iterations", str(args.iterations),
                       "--mode", mode, "--tsa", args.tsa, "--seed", str(args.seed),
                       "--initial", str(args.dataset.parent.parent / "prime" / f"{args.tsa}-prime.csv"),
                       "--out", str(out)]
            if mode == "spatial":
                command += ["--geometry", str(args.geometry), "--fits", str(args.fits)]
            jobs.append((mode, att, epsilon, out, command))

    def run(job):
        mode, att, epsilon, out, command = job
        started = time.perf_counter()
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            return mode, att, epsilon, out, time.perf_counter() - started, None
        except subprocess.CalledProcessError as exc:
            msg = (exc.stderr or exc.stdout or "").strip().splitlines()
            return mode, att, epsilon, out, time.perf_counter() - started, (msg[-1] if msg else f"exit {exc.returncode}")

    results = []
    with ThreadPoolExecutor(max_workers=args.min_workers if hasattr(args, "min_workers") else args.workers) as pool:
        for result in pool.map(run, jobs):
            results.append(result)
            status = "ok" if result[5] is None else f"FAILED: {result[5]}"
            print(f"{result[0]:8s} {result[1]:.2f} eps {result[2]:,} ({result[4]:.0f}s) {status}", flush=True)

    rows = []
    failed = 0
    for mode, att, epsilon, out, elapsed, error in results:
        if error is not None or not out.exists() or out.stat().st_size == 0:
            failed += 1
            continue
        with out.open() as handle:
            for row in csv.DictReader(handle):
                row["attainment_target"] = att
                row["baseline"] = row["mode"] == "aspatial" and base_aspatial or base_spatial
                row["elapsed_s"] = round(elapsed, 1)
                rows.append(row)
    rows.sort(key=lambda r: (r["mode"], float(r["attainment_target"])))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(f"wrote {args.out} ({len(rows)} points, {failed} infeasible)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
