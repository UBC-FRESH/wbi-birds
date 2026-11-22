"""Bird-free even-flow search by multi-start on the fast resident-state SA.

Runs K independent two-stage chains (level, then level + band) in parallel per rung and
keeps the best. Doubling per-chain iterations until the best level/objective agree within
a tolerance. Same search as prime_schedule.py, which is the patched fast path.
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing prime output (default: refuse)")
    p.add_argument("--record", type=Path, default=None)
    p.add_argument("--iterations", nargs="+", type=int,
                   default=[500_000, 1_000_000, 2_000_000])
    p.add_argument("--starts", type=int, default=8)
    p.add_argument("--pull", type=float, default=40e6)
    p.add_argument("--band", type=float, default=5.0)
    p.add_argument("--band-weight", type=float, default=1e9)
    p.add_argument("--tolerance", type=float, default=0.02)
    p.add_argument("--prime-script", type=Path,
                   default=Path(__file__).with_name("prime_schedule.py"))
    a = p.parse_args()
    if a.out.exists() and not a.force:
        print(f"refusing to overwrite {a.out}; pass --force or write to a *-check.csv path",
              file=sys.stderr, flush=True)
        return 2

    work = a.out.parent / "multistart" / a.dataset.name
    work.mkdir(parents=True, exist_ok=True)
    history: list[dict] = []
    previous: tuple[float, float] | None = None
    converged = False
    best_final: Path | None = None

    for iterations in a.iterations:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print(f"[{a.dataset.name}] rung {iterations:,} start {stamp} starts {a.starts}", flush=True)
        procs = []
        for start in range(a.starts):
            out = work / f"rung-{iterations}-start-{start}.csv"
            cmd = [sys.executable, str(a.prime_script), "--dataset", str(a.dataset),
                   "--iterations", str(iterations), "--pull", str(a.pull), "--band", str(a.band),
                   "--band-weight", str(a.band_weight), "--seed", str(1000 + start),
                   "--out", str(out)]
            procs.append((out, subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)))
        results = []
        for out, proc in procs:
            text = proc.communicate()[0]
            m = STAGE2.search(text)
            if proc.returncode != 0 or m is None:
                print(f"  start failed: {text.strip()[-400:]}", flush=True)
                continue
            results.append({"schedule": out, "level": float(m.group(1)), "objective": float(m.group(2))})
        if not results:
            raise SystemExit("no start completed")
        best = min(results, key=lambda r: (r["objective"], -r["level"]))
        record = {"iterations": iterations, "starts": len(results),
                  "level_M_m3_yr": best["level"], "objective": best["objective"],
                  "spread_level": round(max(r["level"] for r in results) - min(r["level"] for r in results), 4)}
        history.append(record)
        print(json.dumps(record), flush=True)
        if a.record is not None:
            a.record.parent.mkdir(parents=True, exist_ok=True)
            a.record.write_text(json.dumps({"dataset": str(a.dataset), "converged": False,
                                            "history": history, "final": str(a.out)}, indent=2) + "\n")
        best_final = best["schedule"]
        if previous is not None:
            dl = abs(best["level"] - previous[0]) / max(best["level"], 1e-12)
            do = abs(best["objective"] - previous[1]) / max(abs(best["objective"]), 1e-12)
            if dl <= a.tolerance and do <= a.tolerance:
                converged = True
                break
        previous = (best["level"], best["objective"])

    if best_final is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(best_final, a.out)
    record = {"dataset": str(a.dataset), "converged": converged, "tolerance": a.tolerance,
              "starts": a.starts, "history": history, "final": str(a.out)}
    if a.record is not None:
        a.record.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
