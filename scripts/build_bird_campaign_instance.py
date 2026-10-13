"""Build a bird-campaign instance from femic ws3 sections with a contract response table (E-P4.11).

For one management unit this:

1. stages the femic ws3 section bundle into ``<out>/inputs/ws3/``;
2. writes ``manifest.yaml``, ``config/run.yaml`` and ``config/species.yaml``;
3. builds the ws3 model and enumerates every ``(development type, age)`` the
   campaign's action codes can reach (:func:`wbi_birds.bird.reachable_state_space`);
4. evaluates the refit Poisson response on that state space
   (``exp(b0 + b1*softwood + b2*hardwood + b3*age)``) and writes
   ``bird/response_table.csv`` with its provenance sidecar;
5. checksums the staged inputs and validates the instance with the engine's
   own validator.

The response is the fitted expected count on the exact link (log-link), embedded
as a fixed per-(development type, age) LP coefficient. The fit covariates are the
accepted unit contract (volume allocation), so the state vector is
``(swdvol, hwdvol, age)`` from the planning yield curves.

Usage::

    python scripts/build_bird_campaign_instance.py \
        --ws3-dir <femic-instance>/output/ws3 --model tsa24 --unit TSA24 \
        --out <campaign>/TSA24/instance --refit results/bird/rbnu_contract_fit.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

from wbi_birds import __version__
from wbi_birds.bird import build_response_table, reachable_state_space
from wbi_birds.instance import ERROR, validate_instance
from wbi_birds.mapping import load_ws3_sections, stage_ws3_sections
from wbi_birds.model import build_model
from wbi_birds.registry import GUILDS, SUITE_GUILDS
from wbi_birds.responses import merge_response_table

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(path: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "describe", "--always", "--dirty", "--abbrev=7"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _species_config(codes: list[str]) -> dict:
    entries = [{"code": code, "guild": SUITE_GUILDS[code]} for code in codes]
    return {"species": entries, "guilds": list(GUILDS)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ws3-dir", type=Path, required=True)
    parser.add_argument("--model", required=True, help="ws3 model stem, e.g. tsa24.")
    parser.add_argument("--unit", required=True, help="Management-unit label, e.g. TSA24.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--refit", type=Path, required=True, help="Refit JSON with fit.coefficients."
    )
    parser.add_argument("--species", default="rebnut")
    parser.add_argument("--acode", default="cc", help="Harvest action code (default: cc).")
    parser.add_argument("--horizon-years", type=int, default=200)
    args = parser.parse_args(argv)

    refit = json.loads(args.refit.read_text(encoding="utf-8"))
    coefficients = refit["fit"]["coefficients"]
    beta = [coefficients[term] for term in ("intercept", "softwood", "hardwood", "age")]

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    bundle = load_ws3_sections(args.ws3_dir, args.model)
    staged = stage_ws3_sections(bundle, out)

    (out / "config").mkdir(parents=True, exist_ok=True)
    (out / "results").mkdir(parents=True, exist_ok=True)
    (out / "config" / "run.yaml").write_text(
        yaml.safe_dump(
            {
                "management_unit": {"id": args.unit, "name": args.unit},
                "horizon_years": args.horizon_years,
                "model": {"harvest_acodes": [args.acode]},
                "even_flow": {"epsilon": 0.10},
                "utilization": 0.85,
                "scenarios": {"epsilon_steps": 11, "mode": "frontier"},
                "solver": {"backend": "highs", "options": {}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (out / "config" / "species.yaml").write_text(
        yaml.safe_dump(_species_config([args.species]), sort_keys=False), encoding="utf-8"
    )

    model, stats = build_model(out)
    states = reachable_state_space(model, acodes=("null", args.acode))

    def predict(softwood: float, hardwood: float, age: int) -> float:
        eta = beta[0] + beta[1] * softwood + beta[2] * hardwood + beta[3] * age
        return math.exp(max(min(eta, 30.0), -30.0))

    table = build_response_table(
        model,
        args.species,
        predict,
        states=states,
        source={
            "fit": "refit_rbnu_contract",
            "definition": refit["definition"],
            "link": "log (exp of the linear predictor)",
            "refit_sha256": _sha256(args.refit),
            "unit": args.unit,
        },
    )
    merge_response_table(out, table)

    checksums = {
        str(path.relative_to(out)): _sha256(path)
        for path in sorted((out / "inputs" / "ws3").iterdir())
    }
    checksums["bird/response_table.csv"] = _sha256(out / "bird" / "response_table.csv")
    manifest = {
        "schema_version": 1,
        "instance_id": f"campaign-rbnu-contract-{args.unit.lower()}",
        "created": date.today().isoformat(),
        "provenance": {
            "femic": {
                "commit": _git_head(REPO_ROOT.parent / "femic"),
                "ws3_dir": str(args.ws3_dir),
            },
            "ws3": {"model": args.model, "staged": staged},
            "bird_model": {
                "definition": refit["definition"],
                "refit": str(args.refit.name),
                "refit_sha256": _sha256(args.refit),
            },
            "engine": {"version": __version__, "commit": _git_head(REPO_ROOT)},
            "build": {"states": len(states), "model_stats": str(stats)},
        },
        "checksums": {"algorithm": "sha256", "files": checksums},
    }
    (out / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    issues = validate_instance(out)
    errors = [issue for issue in issues if issue.severity == ERROR]
    for issue in issues:
        print(f"{issue.severity}: {issue.code}: {issue.message}")
    print(f"states={len(states)} dtypes={stats.dtype_count} unit={args.unit} out={out}")
    if errors:
        print(f"FAILED: {len(errors)} validation error(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
