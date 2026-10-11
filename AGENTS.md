# Agent Operating Notes — wbi-birds

## Project purpose

Simulation engine for the WBI birds manuscript ([`UBC-FRESH/wbi-birds-2021`](https://github.com/UBC-FRESH/wbi-birds-2021)):
ε-constraint tradeoffs between even-flow harvesting and multi-species bird abundance, built on `ws3`.
Pattern repos: `UBC-FRESH/fresh-daugherty` (closest analogue), `UBC-FRESH/fhops`.

## Reuse boundary

- Depend on `UBC-FRESH/ws3` (ForestModel, LP machinery, Model I even-flow + ε constraints). **Do not re-implement ws3.**
- Consume `UBC-FRESH/femic` outputs via a documented file contract; do not import-couple.
- Bird anticipation curves are served by the species-generic module in this repo (lineage: `fitBirdBiomassModel`).
- **Raw eBird data are never redistributed**; derived products only (see manuscript repo `planning/ebird-data-request*.md`). Private raw store: submodule `external/wbi-ebird-data` (DataLad); CI does not init submodules; never publish its content.

## Current repo state

Phase E-P1 (scaffold). Layout: `src/wbi_birds/`, `tests/`, `docs/`, `examples/`, `planning/`, `results/`,
`scripts/`, `data/` (README-only), `.github/workflows/{ci,docs,release}.yml`.

## Planning workflow (lab standard)

- One roadmap phase ↔ one GitHub parent issue ↔ one feature branch (`feature/issue-<N>-<slug>`).
- One roadmap task ↔ one child issue linked from the parent body; ≤3 issue levels.
- Update `ROADMAP.md` + `CHANGE_LOG.md` in the same change set as the work.
- Open a PR from the phase branch when tasks/tests/docs are complete; close the parent after merge.

## Verification (before wrapping any milestone)

- `ruff format --check src tests` · `ruff check src tests` · `pytest`
- Docs build: `sphinx-build -b html docs docs/_build/html -W`
- CI green on the PR.

## Engine defaults

- Solver: **HiGHS** (open) by default; Gurobi optional switch; record solver + version in result metadata.
- Instances: **one per management unit (TSA)**.

## Guardrails

- Scientific scope is frozen by the manuscript roadmap; engine changes that could alter results require an
  issue cross-linked to `UBC-FRESH/wbi-birds-2021#3`.
- Record release/version identifiers for every result-affecting run.
