# Agent Operating Notes — wbi-birds

## Project purpose

Simulation engine for the WBI birds manuscript ([`UBC-FRESH/wbi-birds-manuscript`](https://github.com/UBC-FRESH/wbi-birds-manuscript)):
ε-constraint tradeoffs between even-flow harvesting and multi-species bird abundance, built on `ws3`.
Pattern repos: `UBC-FRESH/fresh-daugherty` (closest analogue), `UBC-FRESH/fhops`.

## Reuse boundary

- Depend on `UBC-FRESH/ws3` (ForestModel, LP machinery, Model I even-flow + ε constraints). **Do not re-implement ws3.**
- `UBC-FRESH/femic` is the control plane for forest-estate model building/running (incl. ws3 via `femic.ws3_bridge`); compose its FreshForge providers/outputs rather than reimplementing model construction. No import-coupling at runtime; coupling = providers + file contracts (femic → `inputs/ws3/` Woodstock sections; see `planning/femic-map.md`; `UBC-FRESH/femic#316`).
- Bird anticipation curves are served by the species-generic module in this repo (lineage: `fitBirdBiomassModel`).
- **Raw eBird data are never redistributed**; derived products only (see manuscript repo `planning/ebird-data-request*.md`). Private raw store: submodule `external/wbi-ebird-data` (DataLad); CI does not init submodules; never publish its content.
- Workflow layer: **FreshForge** — pipeline graphs in `workflows/`, provider `wbi` via the `freshforge.providers` entry point; evidence manifests are the run-record contract; FreshForge stays domain-neutral while this repo owns node execution.

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
- Harvest actions: declared in the instance run config (`model.harvest_acodes`, default `[harvest]`); the engine sets the ws3 harvest flags explicitly (upstream parser gap: `UBC-FRESH/ws3#156`).
- Workflow: FreshForge (pinned in the `workflow` extra); execution hooks land per ROADMAP E-P3–E-P5; see `planning/workflow-blueprint.md`.

## Guardrails

- Scientific scope is frozen by the manuscript roadmap; engine changes that could alter results require an
  issue cross-linked to `UBC-FRESH/wbi-birds-manuscript#3`.
- Record release/version identifiers for every result-affecting run.
- **Decision authority:** GP is the sole decision-maker and project driver. TM and EM are nominal co-authors with end-stage, non-blocking review only. No engine task, issue, or PR waits on their input (manuscript repo `AGENTS.md` → Decision authority).
