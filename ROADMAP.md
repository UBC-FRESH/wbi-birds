# wbi-birds Roadmap

Program context: [`UBC-FRESH/wbi-birds-2021`](https://github.com/UBC-FRESH/wbi-birds-2021) → `ROADMAP.md` (v2).
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
- [x] Issue tree created + linked from paper #3 (`UBC-FRESH/wbi-birds-2021#3`)
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

Goal: species-generic anticipation curves; legacy RBNU parity anchor.

- [x] Coefficient/curve module — `wbi_birds.bird` (per-dtype `bird = c1*swdvol + c2*hwdvol + c3*age + c4`; LP-materialized row; `measure_scope`)
- [ ] EBD-derived ingestion path (auk-style filtering; derived tables only)
- [x] Species/guild registry — `wbi_birds.registry` + taxonomy snapshot (9-species suite; validator checks codes/names; fixture carries the full suite)
- [ ] FreshForge `run_node` hooks for `ingest_ebd` / `fit_antifunction`

## E-P5 — Verification & parity

Goal: reproduce legacy RBNU / 5-TSA results within tolerance; diagnostics.

- [ ] Legacy parity fixtures + tolerance report
- [ ] `results/REPRODUCIBILITY.md`
- [ ] Anomaly adjudication with the manuscript claims map
- [ ] FreshForge `run_node` hooks for `verify_parity` / `compute_frontiers` / `analyze_frontiers`

## E-P6 — Docs, examples, release

Goal: `v1.0.0` release with DOI.

- [ ] Docs site complete (quickstart, contracts, CLI); GitHub Pages publishing
- [ ] Example instance + notebook
- [ ] Tag `v1.0.0` + Zenodo DOI + `CITATION.cff`
- [ ] Self-bootstrapping README acceptance: fresh environment + README (public lane) reproduces headline results
