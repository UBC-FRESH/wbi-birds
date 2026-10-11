# Change Log

Newest entries last. Every deliverable appends a dated entry (see `AGENTS.md`).

## 2026-10-11 — Repo bootstrap (E-P1)

- Repo created (`UBC-FRESH/wbi-birds`, public, MIT) with initial scaffold: src layout, CLI skeleton,
  docs, CI/docs/release workflows, planning surfaces.
- Engine phase tree E-P1..E-P6 recorded; paper-side link: `UBC-FRESH/wbi-birds-2021#3`.

## 2026-10-11 — E-P1 complete (scaffold validated)

- CI green: `ci` run 38103589362 (Py 3.11/3.12; install incl. ws3, ruff, pytest), `docs` run 38103589358 (`-W`).
- Issue tree linked from `UBC-FRESH/wbi-birds-2021#3`; E-P1 closed. Next: E-P2 (activation after the paper-side P2 closes).

## 2026-10-11 — E-P2 activated; E-P2.1 contract draft

- E-P2 children opened: #7 (instance contract), #8 (femic consumption path), #9 (schemas); phase branch `feature/issue-2-ep2-data-contract`.
- E-P2.1: `planning/data-contract.md` v0.1 draft (layout, manifest, run/species/coefficient configs, validation rules, boundaries, open questions).

## 2026-10-11 — E-P2: private data store wired; decisions resolved

- Private DataLad dataset `UBC-FRESH/wbi-ebird-data` created; wired as `external/wbi-ebird-data` submodule of this repo.
- E-P2.1 decisions resolved: HiGHS default solver (Gurobi switch documented), per-management-unit (TSA) instances, instance-local coefficients.

## 2026-10-11 — FreshForge workflow layer adopted

- Provider `wbi` added (plan-only; `src/wbi_birds/forge.py`, entry point `freshforge.providers`) declaring 8 pipeline node types.
- Specs: `workflows/wbi_pipeline.yaml`, `workflows/wbi_pipeline_template.yaml`, `workflows/wbi_mu_matrix.yaml` (5 MUs); blueprint: `planning/workflow-blueprint.md`.
- Validated with freshforge 0.1.0a5: `providers` (wbi listed), `validate` + `plan` green, `matrix expand` = 5 cases, 0 diagnostics. Execution hooks scheduled per ROADMAP E-P3–E-P5.

## 2026-10-11 — femic ownership correction + self-bootstrapping requirement

- femic acknowledged as control plane for forest-estate model building/running (incl. ws3 via `femic.ws3_bridge`); target graph composes femic model-build stages; interim `compile_instance`/`build_model` adapters flagged for E-P3 swap. Request issue: `UBC-FRESH/femic#316`.
- Self-bootstrapping requirement recorded: fresh env + README → headline results (public lane = released derived inputs; team lane = private annex). README bootstrap section added; acceptance at E-P6.
- Blueprint/contract/AGENTS/ROADMAP updated.

## 2026-10-11 — E-P2.1 validator complete; B3 support noted

- Instance validator implemented (`wbi_birds.instance`, CLI `wbi-birds instance validate`): required files/schemas, species-coefficient consistency, checksum verification, raw-eBird boundary scan. Fixture + 6 tests; suite green (11 passed). E-P2.1 (#7) closed.
- B3 formulation locked upstream to option 1 (habitat-only reserve network vs integrated ε-constraints, `UBC-FRESH/wbi-birds-2021#14`); engine support task added under E-P3.

## 2026-10-11 — E-P2.3 schemas complete

- `wbi_birds.scenarios`: pydantic schemas (ScenarioSpec/ScenarioSet/ScenarioResult + solver/even-flow config) with YAML/JSON round-trip helpers and consistency rules (ordered ε levels, unique ids, MU match). 11 new tests; suite 22 passed. E-P2.3 (#9) closed.

## 2026-10-11 — E-P2.2 femic mapping complete; E-P2 phase closed

- `wbi_birds.mapping` (load/stage ws3 Woodstock section files) + `planning/femic-map.md` v1 (boundary, contract, open questions for femic#316); real `tsa24_clipped` fixture from the ws3 examples.
- Suite green: 27 tests. E-P2 children (#7/#8/#9) closed; parent #2 closed; phase PR opened to main.

## 2026-10-11 — E-P2 merged to main; E-P3 activated

- PR #10 (E-P2 phase) merged to `main` (CI green).
- E-P3 activated: children #11-#15; branch `feature/issue-3-ep3-core-engine`.

## 2026-10-11 — E-P3.1 ws3 model builder

- `wbi_birds.model.build_model(instance_root)`: builds a ws3 ForestModel from `inputs/ws3/` + run config (five section imports; period/horizon derivation; optional `model` block overrides); `mapping.locate_ws3_bundle` discovers the bundle stem. `ModelStats` records model/dtype/action/transition/curve counts. 5 tests; suite 32 passed. E-P3.1 (#11) closed.
