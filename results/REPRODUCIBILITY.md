# Reproducibility — wbi-birds engine

Status: **draft** — framework complete; finished with the release artifacts (E-P6).

Every result-affecting run records release/solver provenance in its result metadata
(`provenance` block written next to each scenario table).

## Environment

- Python ≥ 3.11. Install the engine with the verification + workflow extras:
  `pip install -e ".[dev,workflow]"` (FreshForge is pinned via the `workflow` extra;
  raw eBird data are never part of the package).
- Solver: HiGHS by default (`ws3.opt.SOLVER_HIGHS`); the solver + version is recorded
  per scenario result.

## Verification

```bash
ruff format --check src tests
ruff check src tests
pytest
sphinx-build -b html docs docs/_build/html -W
```

CI runs the same steps (`.github/workflows/{ci,docs}.yml`).

## Fixture pipeline (no private data)

The full chain — ingest → fit → compile → build → bird scenario — runs via FreshForge
on packaged fixtures: see `tests/test_forge_full_chain.py` (five-node workflow with
the `--evidence` manifest). Capability smoke graphs live in `workflows/`.

## Full chain (real data)

Prerequisites:

- private eBird extract + coefficients (request runbook: manuscript repo
  `planning/ebird-data-request-process.md`; raw data are never redistributed),
- femic model-build bundle for the AOI (`UBC-FRESH/femic#316`),
- one instance per management unit (`planning/data-contract.md`).

Per-MU runs use the template graph `workflows/wbi_pipeline_template.yaml` with the
cases in `workflows/wbi_mu_matrix.yaml`.

## Legacy parity

```bash
python scripts/parity_check.py <instance> <reference.csv> --label <mu> [--strict]
```

Reference acquisition + tolerance policy: `planning/parity-reference-acquisition.md`.
Reports land in `<instance>/results/parity/`.

## Manuscript artifacts

- Figures/tables: pending the campaign (manuscript roadmap P5) plus the analysis hooks
  (`compute_frontiers` / `analyze_frontiers`).
- Release: version tag + Zenodo DOI — pending.
