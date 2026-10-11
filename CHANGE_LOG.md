# Change Log

Newest entries last. Every deliverable appends a dated entry (see `AGENTS.md`).

## 2026-10-11 — Repo bootstrap (E-P1)

- Repo created (`UBC-FRESH/wbi-birds`, public, MIT) with initial scaffold: src layout, CLI skeleton,
  docs, CI/docs/release workflows, planning surfaces.
- Engine phase tree E-P1..E-P6 recorded; paper-side link: `UBC-FRESH/wbi-birds-manuscript#3`.

## 2026-10-11 — E-P1 complete (scaffold validated)

- CI green: `ci` run 38103589362 (Py 3.11/3.12; install incl. ws3, ruff, pytest), `docs` run 38103589358 (`-W`).
- Issue tree linked from `UBC-FRESH/wbi-birds-manuscript#3`; E-P1 closed. Next: E-P2 (activation after the paper-side P2 closes).

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
- B3 formulation locked upstream to option 1 (habitat-only reserve network vs integrated ε-constraints, `UBC-FRESH/wbi-birds-manuscript#14`); engine support task added under E-P3.

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

## 2026-10-11 — E-P3.2 ε-constraint scenario runner

- `wbi_birds.runner`: `ProblemSpec` + `run_scenario()` — objective (harvest even-flow via `cflw_e`), per-period constraint floors (scalar or period-keyed mapping) materialized via `cgen_data` lb rows, HiGHS default, solver backend + version + objective value recorded in `ScenarioResult` provenance. Series computed through the canonical `compile_schedule → apply_schedule → compile_product` path.
- Fixture smoke: nadir solve optimal (harvest ≈ 332,914.7 m³ on `tsa24_clipped`), binding per-period floor respected, infeasible floors reported as `infeasible`, even-flow scenario solves. Suite: 38 tests green.
- Upstream find (filed): `UBC-FRESH/ws3#156` — the Woodstock ACTION importer drops the harvest flag (`*ACTION <code> Y` → `is_harvest = 0`), zeroing any `is_harvest()`-filtered coefficient function (including the shipped 022 notebook pattern). Engine workaround: explicit harvest action codes from instance config (`model.harvest_acodes`), set after import.
- E-P3.2 (#12) closed.

## 2026-10-11 — E-P3.3 result outputs; E-P3.4 FreshForge execution hooks

- `wbi_birds.results`: deterministic per-scenario CSV tables + YAML records under `<instance>/results/scenarios/<mu>/`; artifacts referenced from records; contract doc updated. (#13 closed)
- FreshForge hooks: `wbi.build_model` / `wbi.run_scenarios` execute end-to-end; `freshforge run` smoke writes results + a durable evidence manifest on the fixture instance. (#14 closed)
- Dependency: `freshforge` pinned to checkout commit `5bce95b56146613c7c01950403fb717d3af886d7` (evidence manifests unreleased past PyPI 0.1.0a5); sunset = switch to a version pin at the next freshforge alpha. Suite: 42 tests green.

## 2026-10-11 — E-P3.5 B3 comparison + femic compile adapter; E-P3 phase complete

- `wbi_birds.reserves`: habitat-only reserve selection (initial-inventory age criterion) + harvest exclusion. `wbi_birds.b3`: sequential-vs-integrated comparison, matched-outcome interpolation, deterministic JSON record (`results/b3/...`); explicit unmatched-note when the target is outside the frontier (proxy row until E-P4).
- `wbi.compile_instance` execution hook: femic ws3-bundle → instance (`inputs/ws3/` + `management_unit` update); full chain (bundle → instance → model → scenario) runs via `freshforge run` with evidence (chain smoke green).
- Suite: 47 tests green. E-P3 children #11–#15 all closed; phase PR opened to main.

## 2026-10-11 — E-P3 merged to main (PR #16, CI green); E-P4 activated

- PR #16 merged; phase branch deleted.
- E-P4 activated: children #17-#20; branch `feature/issue-4-ep4-bird-module`.

## 2026-10-11 — E-P4.1 bird anticipation row

- `wbi_birds.bird`: `AnticipationCoefficients` (paper/legacy `birdaf_*` naming), per-dtype `bird_unit_value` (`c1*swdvol + c2*hwdvol + c3*age + c4`), LP row coefficient compilation; `load_coefficients(instance, species)`.
- Runner: `bird_coefficients` + `measure_scope` (`harvest` | `landscape`); the bird row is materialized on every period and its series is read **exactly from the LP solution** — post-hoc schedule reconstruction proved lossy for null-area accounting (diagnosed with per-constraint LHS values).
- Findings: ws3 complex-yield resolvers cannot nest calls (KeyError) — the engine owns the row directly and works for runtime-created development types. Fixture `bird/coefficients.yaml` now carries the paper's RBNU coefficients. Suite: 51 tests green. E-P4.1 (#17) closed.

## 2026-10-11 — E-P4.2 species/guild registry

- `wbi_birds.taxonomy` (generated from the curated eBird taxonomy fetch: 9 codes with names) + `wbi_birds.registry` (manuscript suite: mature_conifer x4, mixedwood x2, early_seral x2, cavity x1; `load_registry`; `validate_taxonomy`).
- Instance validator extended: unknown species code = error; common-name mismatch = warning. Fixture now carries the full nine-species suite + coefficients. Suite: 56 tests. E-P4.2 (#18) closed.

## 2026-10-11 — E-P4.3 EBD-derived ingestion

- `wbi_birds.ingest`: streaming filter of the private EBD extract (species suite x breeding months, optional complete-checklists-only) into derived point-level CSVs with SHA256-stamped provenance sidecars; legacy `X` -> 0.0 convention; observer identifiers never copied. Tab-delimited fixture with noise rows; 6 tests. Suite: 62 tests. E-P4.3 (#19) closed.

## 2026-10-11 — E-P4.4 fitting + hooks; E-P4 phase complete

- `wbi_birds.fit`: `stage_coefficients` (provided/R-lineage mode, taxonomy-validated, deterministic output) and engine-native Poisson MLE (`fit_poisson_glm`, feature-standardized L-BFGS-B, gradient-based convergence flag); merge preserves other species and marks `source.fit`.
- FreshForge hooks: `wbi.ingest_ebd` and `wbi.fit_antifunction` execute; `wbi.run_scenarios` supports `bird_species` + `measure_scope` (bird row). Full chain smoke: ingest → fit → compile → build → bird scenario via `freshforge run` with evidence; positive landscape bird total verified.
- Suite: 69 tests green. E-P4 children #17–#20 all closed; phase PR opened.

## 2026-10-11 — E-P4 merged to main (PR #21, CI green); E-P5 activated

- PR #21 merged; phase branch deleted.
- E-P5 activated: children #22-#24; branch `feature/issue-5-ep5-parity` (real parity gated on femic#316).

## 2026-10-11 — E-P5.1 parity tolerance module

- `wbi_birds.parity`: engine/reference long-format alignment, abs+rel tolerance policy, deterministic comparison records + JSON/Markdown reports (`results/parity/`); missing/extra rows are explicit failures with reasons. 6 tests; suite 75 green. E-P5.1 (#22) closed.

## 2026-10-11 — E-P5.2 verify_parity hook

- `wbi_birds.parity.compare_instance_results`: scans `<instance>/results/scenarios/**`, derives MU/scenario from the path, compares against long-format reference tables.
- FreshForge `wbi.verify_parity` hook: writes `results/parity/<label>-parity.{json,md}`, `parity.failed` warnings per metric, `strict: true` fails the node; parity summary in node outputs (and thus the evidence manifest). 2 hook tests (within-tolerance + warning/strict-failure); suite 77 green. E-P5.2 (#23) closed.

## 2026-10-11 — E-P5.3 prep (acquisition path, CLI, reproducibility draft)

- `planning/parity-reference-acquisition.md`: legacy reference locations (outputs not in the repos), export checklist to the long-format contract, acquisition options, gating.
- `scripts/parity_check.py`: standalone parity CLI (reports under `results/parity/`; `--strict` exit code).
- `results/REPRODUCIBILITY.md`: draft framework (environment, verification, fixture chain, real-data prerequisites, parity, release placeholders). CLI tests added; suite 79 green.
