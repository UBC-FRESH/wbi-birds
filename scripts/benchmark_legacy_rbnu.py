"""Benchmark the native bird regression against the legacy RBNU reference (E-P4.7).

Requires the private data submodule (``external/wbi-ebird-data``) to be
initialised and the ``rbnu-legacy`` design matrix present. Usage::

    python scripts/benchmark_legacy_rbnu.py [--tight]

``--tight`` compares against the reconstructed reference (last run) instead of
the rounded 2019 reference.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from wbi_birds.regression import fit_poisson_glm

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN = REPO_ROOT / "external" / "wbi-ebird-data" / "derived" / "rbnu-legacy" / "rbnu_legacy_design.csv"
REFERENCE = REPO_ROOT / "tests" / "fixtures" / "legacy_rbnu_reference.json"


def main() -> int:
    if not DESIGN.is_file():
        print(f"private design matrix not found: {DESIGN}")
        print("initialise the submodule and `datalad get` the derived data first.")
        return 2
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    target = reference["reconstructed_reference" if "--tight" in sys.argv else "r_2019_reference"]

    frame = pd.read_csv(DESIGN)
    result = fit_poisson_glm(
        frame[["softwood", "hardwood", "age"]].to_numpy(),
        frame["observation_count"].to_numpy(),
        ("softwood", "hardwood", "age"),
    )

    print(f"{'term':10s} {'native':>16s} {'reference':>16s} {'rel.err':>10s}")
    failed = False
    for term, expected in target["coefficients"].items():
        actual = result.coefficients[term]
        rel = abs(actual - expected) / abs(expected)
        flag = "" if rel < 1e-6 else ("  <-- CHECK" if rel > 1e-3 else "")
        failed = failed or rel > 1e-3
        print(f"{term:10s} {actual:16.10e} {expected:16.10e} {rel:10.2e}{flag}")
    print(f"n: native {result.n} reference {target['n']}")
    print(f"null deviance: native {result.null_deviance:.3f} reference {target['null_deviance']}")
    print(f"residual deviance: native {result.residual_deviance:.3f} reference {target['residual_deviance']}")
    print(f"AIC: native {result.aic:.3f} reference {target['aic']}")

    if abs(result.n - target["n"]) > 5:
        failed = True
        print("FAIL: n differs from the reference by more than 5 rows")
    if abs(result.residual_deviance - target["residual_deviance"]) > 1.0:
        failed = True
        print("FAIL: residual deviance differs from the reference by more than 1")
    print("PASS" if not failed else "FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
