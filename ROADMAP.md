# wbi-birds Roadmap

Program context: [`UBC-FRESH/wbi-birds-manuscript`](https://github.com/UBC-FRESH/wbi-birds-manuscript) → `ROADMAP.md` (v2).
This repo implements paper **Phase 3** (engine reimplementation).

## One-liner

ε-constraint harvest–bird-abundance tradeoff engine (ws3-based) that regenerates every headline result of
the WBI birds manuscript, released with a DOI.

## Issue tracker map

- E-P1 Scaffold & contracts — #1
- E-P2 Data contract & instance compilation — #2
- E-P3 Core engine (model builder + scenario runner) — #3
- E-P4 Bird module (species-generic anticipation curves) — #4
- E-P5 Verification & parity (legacy RBNU anchor) — #5
- E-P6 Docs, examples, release v1.0.0 — #6

## E-P1 — Scaffold & contracts

Status: **complete** (2026-10-11)

- [x] Repo scaffold + initial commit (`a5c6520`)
- [x] CI workflows validated (`ci` 38103589362, `docs` 38103589358; release dry-run at E-P6)
- [x] Issue tree created + linked from paper #3 (`UBC-FRESH/wbi-birds-manuscript#3`)
- [x] Reuse boundary contract documented (ws3 / femic / bird lineage)

## E-P2 — Data contract & instance compilation

Status: **complete** (2026-10-11).

Goal: documented instance layout + provenance; femic-consumption contract; scenario/result schemas.

- [x] Instance directory contract + validation (`wbi-birds instance validate`; fixture tests green)
- [x] femic output consumption path — `planning/femic-map.md` v1 + `wbi_birds.mapping` (fixture-tested with a real `tsa24_clipped` slice)
- [x] Scenario/result schemas (pydantic) + round-trip tests (`wbi_birds.scenarios`; suite green)

Child issues: #7 (instance contract), #8 (femic path), #9 (schemas). Phase branch: `feature/issue-2-ep2-data-contract`.

- [x] FreshForge workflow layer adopted (plan-only provider + pipeline/matrix specs) — `planning/workflow-blueprint.md`
- [ ] AOI model-build pipeline dependency (femic+FreshForge, TSA08/16/24/40/41) — `UBC-FRESH/femic#316`

- [x] Private raw-data store submodule (`external/wbi-ebird-data`, DataLad, private)

## E-P3 — Core engine

Phase branch: `feature/issue-3-ep3-core-engine`. Child issues: #11 (model builder), #12 (scenario grid), #13 (outputs), #14 (FreshForge hooks), #15 (femic composition + B3).

Status: **complete** (2026-10-11).

Goal: model builder (Model I even-flow + ε constraints) + scenario runner.

- [x] ws3 model builder from the instance contract (`wbi_birds.model`; fixture model builds; stats recorded)
- [x] ε-constraint scenario grid runner — `wbi_birds.runner` (per-period floors, even-flow bands, HiGHS; fixture smoke tests green)
- [x] Output contract — `wbi_birds.results` CSV tables + YAML records under `<instance>/results/` (deterministic; fixture-tested)
- [x] B3 support — `wbi_birds.reserves` + `wbi_birds.b3`: habitat-only network vs integrated ε results (matched-outcome interpolation + JSON record)
- [ ] Solver config: HiGHS default; Gurobi switch documented; backend recorded in run metadata
- [x] FreshForge `run_node` hooks for `build_model`/`run_scenarios` — `freshforge run` smoke + durable evidence manifest green
- [x] femic composition — interim `compile_instance` adapter (femic ws3-bundle → instance), chain-tested; swap to femic stages when `femic#316` lands

## E-P4 — Bird module

Phase branch: `feature/issue-4-ep4-bird-module`. Child issues: #17 (anticipation row), #18 (registry), #19 (EBD ingestion), #20 (hooks + bird-row smoke).

Status: **complete** (2026-10-11); extension E-P4.5 (#33, 2026-10-12).

Goal: species-generic anticipation curves; legacy RBNU parity anchor.

- [x] Coefficient/curve module — `wbi_birds.bird` (per-dtype `bird = c1*swdvol + c2*hwdvol + c3*age + c4`; LP-materialized row; `measure_scope`)
- [x] EBD-derived ingestion path — `wbi_birds.ingest` (streaming suite/month/complete filters; derived CSV + provenance sidecar; no observer IDs)
- [x] Species/guild registry — `wbi_birds.registry` + taxonomy snapshot (9-species suite; validator checks codes/names; fixture carries the full suite)
- [x] FreshForge `run_node` hooks for `ingest_ebd` / `fit_antifunction` — full five-node chain smoke with evidence green
- [x] Ensemble response embedding — `wbi_birds.responses` + `bird/response_table.csv`; arbitrary (non-linear) fitted responses evaluated exactly on the **reachable** state space (`reachable_state_space` dry-materials transition DTs); instance validation accepts response table and/or coefficients; `fit_antifunction` mode `response` (#33)
- [x] Native Python regression — `wbi_birds.regression` + `wbi_birds.covariates`; ports `fitBirdBiomassModel` (kNN age projection, species-biomass scaling/wood-type aggregation, Poisson GLM with SEs/z/p/deviance/AIC, stepwise AIC); `fit poisson` / `fit stage-response` CLI; `rasterio` optional `[covariates]` extra; R/SpaDES no longer required (#35)
- [x] Private eBird data lane — `external/wbi-ebird-data` submodule (CI never initialises it); `wbi_birds.ingest` accepts the as-received `.zip`; legacy RBNU benchmark (`scripts/benchmark_legacy_rbnu.py`, gated test) reproduces the 2019 R fit from the reconstructed design matrix (#37)

## E-P5 — Verification & parity

Phase branch: `feature/issue-5-ep5-parity`. Child issues: #22 (tolerance module), #23 (report + hook), #24 (legacy reference + real parity run — gated on `UBC-FRESH/femic#316`).

Goal: reproduce legacy RBNU / 5-TSA results within tolerance; diagnostics.

- [x] Legacy parity tolerance module — `wbi_birds.parity` (alignment, abs+rel tolerances, deterministic reports; fixture tests)
- [x] `results/REPRODUCIBILITY.md` — draft (framework; release completion in E-P6)
- [x] `scripts/parity_check.py` + `planning/parity-reference-acquisition.md` — standalone CLI + acquisition path (real run: #24)
- [ ] Anomaly adjudication with the manuscript claims map
- [x] FreshForge `run_node` hook for `verify_parity` — instance-wide comparison vs long-format reference tables; `strict` gating; JSON+Markdown reports under `results/parity/`
- [x] Bird-objective solves (maximum bird abundance endpoint) — `ProblemSpec.objective_expr='bird'` + `flow_expr` (#31)
- [ ] FreshForge hooks for `compute_frontiers` / `analyze_frontiers` (analysis layer)
- [x] Five-TSA genuine-model campaign baselines (THLB-filtered, 200y/10y, ε = 0.1) — recorded in `planning/femic-map.md`; legacy parity (#24) still gated on the legacy reference archive

## E-P6 — Docs, examples, release

Phase branch: `feature/issue-6-ep6-release`. Child issues: #26 (docs site), #27 (example + notebook), #28 (release).

Goal: `v1.0.0` release with DOI.

- [x] Docs site complete (quickstart, concepts, workflows, parity, CLI, reproducibility, API reference); GitHub Pages publishing — https://ubc-fresh.github.io/wbi-birds/
- [x] Example instance + notebook — `examples/quickstart.ipynb` (executed in CI), `workflows/wbi_example.yaml`, packaged reference table
- [x] `v1.0.0` release metadata: version bump, `CITATION.cff`, `.zenodo.json`, GitHub-release workflow; tag pushed at phase merge — Zenodo DOI deposit pending integration (#29)
- [x] Self-bootstrapping README acceptance — fresh clone -> install -> 79 tests -> example notebook 5/5 (recorded in `results/REPRODUCIBILITY.md`)
