"""Island-mode bird-free even-flow search, doubling per-island iterations to convergence.

Runs the engine's parallel island SA (elite migration) for two stages -- level only,
then level + the hard even-flow band -- and stops when successive doublings agree on
realized level and objective within a tolerance.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu python scripts/island_prime.py \
      --dataset campaigns/.../full-landscape/tsa41 \
      --out campaigns/.../prime/tsa41-prime.csv \
      --record campaigns/.../dual/prime-convergence-tsa41.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prime_schedule import level_yaml  # noqa: E402

HARVEST = "product.HarvestedVolume.managed.Total.CC"


def run_stage(dataset: Path, targets: Path, out: Path, iterations: int, islands: int,
              threads: int, episodes: int, seed: int, initial: Path | None) -> dict:
    ws4 = Path(sys.executable).with_name("ws4")
    command = [
        str(ws4), "optimize",
        "--dataset", str(dataset), "--targets", str(targets),
        "--engine", "sa", "--islands", str(islands), "--threads", str(threads),
        "--episodes", str(episodes), "--iterations", str(iterations),
        "--years", "200", "--seed", str(seed), "--out", str(out),
    ]
    if initial is not None:
        command += ["--initial-schedule", str(initial)]
    started = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    if result.returncode != 0:
        raise RuntimeError(f"stage failed:\n{result.stderr[-2000:]}")
    summary = json.loads((out / "summary.json").read_text())
    return {"objective": float(summary["incumbent_objective"]), "seconds": round(elapsed, 1),
            "schedule": out / "schedule.csv"}


def harvest_level(report: Path) -> float:
    import csv

    values = []
    with report.open() as handle:
        for row in csv.DictReader(handle):
            if row["account"] == HARVEST and row["kind"] == "level":
                values.append(float(row["value"]))
    return sum(values) / len(values) / 10 / 1e6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument("--iterations", nargs="+", type=int,
                        default=[250_000, 500_000, 1_000_000, 2_000_000])
    parser.add_argument("--islands", type=int, default=8)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--pull", type=float, default=40e6)
    parser.add_argument("--band", type=float, default=5.0)
    parser.add_argument("--band-weight", type=float, default=1e9)
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    work = Path(f"/tmp/opencode/island-prime-{args.dataset.name}")
    work.mkdir(parents=True, exist_ok=True)
    stage1 = work / "stage1.yaml"
    stage2 = work / "stage2.yaml"
    stage1.write_text(level_yaml(args.pull, None, args.band_weight))
    stage2.write_text(level_yaml(args.pull, args.band, args.band_weight))

    history: list[dict] = []
    previous: tuple[float, float] | None = None
    final: Path | None = None
    converged = False

    for iterations in args.iterations:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print(f"[{args.dataset.name}] rung {iterations:,} start {stamp}", flush=True)
        s1 = run_stage(args.dataset, stage1, work / f"s1-{iterations}", iterations,
                       args.islands, args.threads, args.episodes, args.seed, None)
        s2 = run_stage(args.dataset, stage2, work / f"s2-{iterations}", iterations,
                       args.islands, args.threads, args.episodes, args.seed, s1["schedule"])
        level = harvest_level(work / f"s2-{iterations}" / "report_targets.csv")
        record = {"iterations": iterations, "level_M_m3_yr": round(level, 4),
                  "objective": s2["objective"], "seconds": s1["seconds"] + s2["seconds"]}
        history.append(record)
        print(json.dumps(record), flush=True)
        if args.record is not None:
            args.record.parent.mkdir(parents=True, exist_ok=True)
            args.record.write_text(json.dumps(
                {"dataset": str(args.dataset), "converged": False, "history": history,
                 "final": str(args.out)}, indent=2) + "\n")
        final = s2["schedule"]
        if previous is not None:
            dl = abs(level - previous[0]) / max(level, 1e-12)
            do = abs(s2["objective"] - previous[1]) / max(abs(s2["objective"]), 1e-12)
            if dl <= args.tolerance and do <= args.tolerance:
                converged = True
                break
        previous = (level, s2["objective"])

    if final is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(final, args.out)
    record = {"dataset": str(args.dataset), "converged": converged, "tolerance": args.tolerance,
              "islands": args.islands, "history": history, "final": str(args.out)}
    if args.record is not None:
        args.record.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
