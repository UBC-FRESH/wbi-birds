# Reproducibility — wbi-birds engine

Status: **complete for `v1.0.0`** (acceptance record below). The real-data
campaign lane remains gated on external inputs (private eBird extract,
`UBC-FRESH/femic#316` model builds, legacy parity archive) — see the manuscript
roadmap.

Every result-affecting run records release/solver provenance in its result
metadata (the `provenance` block written next to each scenario table).

## Environment

- Python ≥ 3.11. Install with the verification, workflow, and examples extras:
  `pip install -e ".[dev,workflow,examples]"` (FreshForge is pinned via the
  `workflow` extra; raw eBird data are never part of the package).
- Solver: HiGHS by default (`ws3.opt.SOLVER_HIGHS`); the solver + version is
  recorded per scenario result.

## Verification

```bash
ruff format --check src tests
ruff check src tests
pytest
sphinx-build -b html docs docs/_build/html -W
python -m build && twine check dist/*
```

CI runs the same steps plus the example notebook
(`.github/workflows/{ci,docs,release}.yml`).

## Self-bootstrapping acceptance (`v1.0.0`)

Fresh clone of the release branch, fresh venv, README public lane:

```bash
git clone https://github.com/UBC-FRESH/wbi-birds
cd wbi-birds
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,workflow,examples]"
pytest -q
python -m nbconvert --to notebook --execute examples/quickstart.ipynb
```

Recorded 2026-10-11 from a fresh clone of `feature/issue-6-ep6-release`:

- `pip install -e ".[dev,workflow,examples]"`: clean install
- `pytest -q`: **79 passed** (~32 s)
- notebook: **executed end-to-end — 5/5 cells, parity 32/32, zero failures**
- environment: Python 3.12, `ws3` 1.1.0a5, FreshForge 0.1.0a5, HiGHS (`highspy`)
  1.15.1, Rich 15.0.0

## Fixture pipeline (no private data)

The full chain — ingest → fit → compile → build → bird scenario → parity — runs
via FreshForge on packaged fixtures:

- `examples/quickstart.ipynb` + `workflows/wbi_example.yaml` (executed in CI);
- integration tests: `tests/test_forge_full_chain.py`,
  `tests/test_verify_parity_hook.py`.

## Campaign lane (real data)

Prerequisites:

- private eBird extract + coefficients (request runbook: manuscript repo
  `planning/ebird-data-request-process.md`; raw data are never redistributed),
- femic model-build bundle for the AOI (`UBC-FRESH/femic#316`),
- one instance per management unit (`planning/data-contract.md`).

Per-MU runs use the template graph `workflows/wbi_pipeline_template.yaml` with
the cases in `workflows/wbi_mu_matrix.yaml`.

## Legacy parity

```bash
python scripts/parity_check.py <instance> <reference.csv> --label <mu> [--strict]
```

Reference acquisition + tolerance policy: `planning/parity-reference-acquisition.md`.
Reports land in `<instance>/results/parity/`.

## Manuscript artifacts and release

- Figures/tables: pending the campaign (manuscript roadmap P5) plus the analysis
  hooks (`compute_frontiers` / `analyze_frontiers`).
- Release: `v1.0.0` tag + GitHub release (sdist/wheel attached). The Zenodo DOI
  deposit is pending enabling the Zenodo–GitHub integration for this repository
  (tracked in #29); `.zenodo.json` + `CITATION.cff` are ready for it.
