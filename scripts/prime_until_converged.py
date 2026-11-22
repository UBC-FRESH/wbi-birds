"""Run the bird-free even-flow problem until it converges, by doubling.

Convergence = successive doublings agree on realized level and objective within a
tolerance. Each rung is a fresh run (same seed), so the criterion is not contaminated
by warm-start carry-over. The final schedule becomes the campaign's warm start and the
harvest ceiling reference.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu python scripts/prime_until_converged.py \
      --dataset campaigns/.../full-landscape/tsa41 \
      --out campaigns/.../prime/tsa41-prime.csv \
      --record campaigns/.../dual/prime-convergence-tsa41.json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

STAGE2 = re.compile(r"stage 2 band=.*harvest ([0-9.]+) M/yr.*obj ([0-9.eE+-]+)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing prime output (default: refuse)")
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument("--iterations", nargs="+", type=int,
                        default=[1_000_000, 2_000_000, 4_000_000, 8_000_000, 16_000_000])
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--pull", type=float, default=40e6)
    parser.add_argument("--band", type=float, default=5.0)
    parser.add_argument("--band-weight", type=float, default=1e9)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--prime-script", type=Path,
                        default=Path(__file__).with_name("prime_schedule.py"))
    parser.add_argument("--previous-level", type=float, default=None,
                        help="level from the last completed rung when resuming")
    parser.add_argument("--previous-objective", type=float, default=None)
    args = parser.parse_args()
    if args.out.exists() and not args.force:
        print(f"refusing to overwrite {args.out}; pass --force or write to a *-check.csv path",
              file=sys.stderr, flush=True)
        return 2

    history: list[dict] = []
    previous: tuple[float, float] | None = (
        (args.previous_level, args.previous_objective or 0.0)
        if args.previous_level is not None
        else None
    )
    converged = False
    final_schedule: Path | None = None

    for iterations in args.iterations:
        rung_dir = args.out.parent / "rungs"
        rung_dir.mkdir(parents=True, exist_ok=True)
        rung = rung_dir / f"prime-rung-{args.dataset.name}-{iterations}.csv"
        command = [
            sys.executable, str(args.prime_script),
            "--dataset", str(args.dataset), "--iterations", str(iterations),
            "--pull", str(args.pull), "--band", str(args.band),
            "--band-weight", str(args.band_weight), "--seed", str(args.seed),
            "--out", str(rung),
        ]
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print(f"[{args.dataset.name}] rung {iterations:,} start {stamp}", flush=True)
        output = ""
        for attempt in (1, 2):
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                output = result.stdout
                break
            print(f"[{args.dataset.name}] rung {iterations:,} attempt {attempt} failed:"
                  f" {result.stderr.strip()[-400:]}", flush=True)
        if not output:
            record = {"dataset": str(args.dataset), "converged": False, "history": history,
                      "error": f"rung {iterations} failed twice", "final": None}
            if args.record is not None:
                args.record.write_text(json.dumps(record, indent=2) + "\n")
            raise SystemExit(1)
        print(output.strip(), flush=True)
        match = STAGE2.search(output)
        if match is None:
            raise RuntimeError(f"could not parse stage 2 line from:\n{output}")
        level, objective = float(match.group(1)), float(match.group(2))
        history.append({"iterations": iterations, "level_M_m3_yr": level, "objective": objective})
        if args.record is not None:
            args.record.parent.mkdir(parents=True, exist_ok=True)
            args.record.write_text(json.dumps(
                {"dataset": str(args.dataset), "converged": False, "history": history,
                 "final": str(args.out)}, indent=2) + "\n")

        if previous is not None:
            dl = abs(level - previous[0]) / max(level, 1e-12)
            do = abs(objective - previous[1]) / max(abs(objective), 1e-12)
            if dl <= args.tolerance and do <= args.tolerance:
                converged = True
                final_schedule = rung
                break
        previous = (level, objective)
        final_schedule = rung

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if final_schedule is not None:
        shutil.copyfile(final_schedule, args.out)
    record = {
        "dataset": str(args.dataset),
        "tolerance": args.tolerance,
        "converged": converged,
        "history": history,
        "final": str(args.out),
    }
    if args.record is not None:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
