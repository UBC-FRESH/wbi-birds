#!/usr/bin/env python3
"""Fail if project scripts invoke ws4 scenarios outside FreshForge.

The only allowed entry point is the FreshForge workflow
``workflows/ws4_evenflow_convergence.yaml``. Provider development may set
``WBI_ALLOW_DIRECT=1`` explicitly; this check exists so that does not become
the normal path.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = re.compile(r"run_spatial_sa\.py|run_state_sa\(")
ALLOW = {
    ROOT / "scripts/run_spatial_sa.py",
    ROOT / "scripts/ws4_evenflow_converge.py",
    ROOT / "scripts/check_scenario_runs.py",
}
# Historical scripts predate the FreshForge-only policy. They remain for provenance
# and are blocked at runtime by the run_spatial_sa guard; new scripts must not be
# added here.
LEGACY = {
    ROOT / "scripts/bench_state_sa.py",
    ROOT / "scripts/dual_campaign.py",
    ROOT / "scripts/guild_frontier.py",
    ROOT / "scripts/prime_schedule.py",
    ROOT / "scripts/staged_band_watch.py",
    ROOT / "scripts/sweep_epsilon.py",
    ROOT / "scripts/sweep_state_sa.py",
    ROOT / "scripts/mature_gradient.sh",
}


def main() -> int:
    hits = []
    for path in sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "scripts").glob("*.sh")):
        if path in ALLOW or path in LEGACY:
            continue
        try:
            text = path.read_text()
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if PATTERNS.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")
    if hits:
        print("Direct ws4 scenario runs are not allowed. Use the FreshForge workflow.")
        print("\n".join(hits))
        return 1
    print("FreshForge-only scenario policy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
