"""Generate and launch the TSA41 two-stage bird scenario sweep via FreshForge.

For each indicator x mode x attainment:
  stage 1: 18M/period level target, nonlinear, bird floor, 1M
  stage 2: 18M/period linear, even-flow +/-5%, bird floor, 2M
Each case is a FreshForge workflow run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path("/srv/shared-data/gep/wbi-birds")
C = ROOT / "campaigns/ws4-five-tsa-2026-11"
REF = ROOT / "reference/wbi-main"
PKG = ROOT / "wbi-birds"
FF = PKG / ".venv/bin/freshforge"
GEN = REF / "workflows/generated/tsa41-bird"
OUT = C / "dual-bird-sweep"
SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
GUILDS = ("mature_conifer", "mixedwood", "early_seral", "cavity")
ALL = (*SPECIES, *GUILDS)


def workflow(case: str, indicator: str, mode: str, epsilon: float,
             stage1: int, stage2: int) -> str:
    out = OUT / case
    return f"""workflow:
  id: {case.replace('-', '_')}
  name: TSA41 bird sweep {case}
nodes:
  - id: bird
    provider: wbi.ws4_evenflow_convergence
    outputs:
      convergence: convergence_record
    parameters:
      dataset: {C}/full-landscape/tsa41
      mode: {mode}
      tsa: tsa41
      bird: {indicator}
      epsilon: {epsilon}
      aspirational: 18000000
      band: 5
      flow_weight: 1000000000
      stage1_level_shape: non_linear
      stage2_level_shape: linear
      stage1_max_iterations: {stage1}
      stage2_max_iterations: {stage2}
      chunk_iterations: 50000
      window: 10
      tolerance: 0.0001
      harvest_tolerance: 0.001
      seed: 42
      initial: {C}/prime/tsa41-prime.csv
      out: {out}
      python: {ROOT}/tmp/ws4-env/bin/python
      driver: {REF}/scripts/ws4_evenflow_converge.py
"""


def run(case_path: Path, case: str) -> str:
    out = OUT / case
    result = out / "result.json"
    if result.exists():
        try:
            data = json.loads(result.read_text())
            return f"skip {case} converged={data.get('converged')}"
        except Exception:
            return f"skip {case} (result exists)"
    out.mkdir(parents=True, exist_ok=True)
    log = out / "freshforge.log"
    with log.open("w") as handle:
        proc = subprocess.run(
            [str(FF), "run", str(case_path), "--workdir", str(PKG),
             "--evidence", str(out / "evidence.json")],
            stdout=handle, stderr=subprocess.STDOUT, check=False,
        )
    if result.exists():
        try:
            data = json.loads(result.read_text())
            return f"done {case} converged={data.get('converged')} rc={proc.returncode}"
        except Exception:
            pass
    return f"failed {case} rc={proc.returncode}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--indicators", default=",".join(ALL))
    ap.add_argument("--modes", default="aspatial,spatial")
    ap.add_argument("--attainments", default="0.80,0.85,0.90,0.95")
    ap.add_argument("--stage1-max", type=int, default=1_000_000)
    ap.add_argument("--stage2-max", type=int, default=2_000_000)
    args = ap.parse_args()

    base = json.loads((C / "dual-full/baselines-tsa41.json").read_text())
    GEN.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    cases = []
    for indicator in args.indicators.split(","):
        for mode in args.modes.split(","):
            b = base.get(mode, {}).get(indicator)
            if b is None:
                print(f"skip {indicator}/{mode}: no baseline")
                continue
            for att_s in args.attainments.split(","):
                att = float(att_s)
                case = f"tsa41-{indicator}-{mode}-{int(round(att * 100)):03d}"
                epsilon = round(att * b)
                path = GEN / f"{case}.yaml"
                path.write_text(workflow(case, indicator, mode, epsilon,
                                         args.stage1_max, args.stage2_max))
                cases.append((path, case))
    print(f"{len(cases)} cases", flush=True)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for msg in pool.map(lambda item: run(*item), cases):
            print(msg, flush=True)
    print("sweep dispatch complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
