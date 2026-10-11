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

Goal: documented instance layout + provenance; femic-consumption contract; scenario/result schemas.

- [ ] Instance directory contract + validation
- [ ] femic output consumption path (documented; tested with fixtures)
- [ ] Scenario/result schemas (pydantic) + round-trip tests

Child issues: #7 (instance contract), #8 (femic path), #9 (schemas). Phase branch: `feature/issue-2-ep2-data-contract`.

## E-P3 — Core engine

Goal: model builder (Model I even-flow + ε constraints) + scenario runner.

- [ ] ws3 model builder from the instance contract
- [ ] ε-constraint scenario grid runner (11 scenarios × TSA × species/guild)
- [ ] Output contract (results tables) + smoke tests

## E-P4 — Bird module

Goal: species-generic anticipation curves; legacy RBNU parity anchor.

- [ ] Coefficient/curve module (softwood / hardwood / age)
- [ ] EBD-derived ingestion path (auk-style filtering; derived tables only)
- [ ] Species/guild registry (suite per manuscript P2.3)

## E-P5 — Verification & parity

Goal: reproduce legacy RBNU / 5-TSA results within tolerance; diagnostics.

- [ ] Legacy parity fixtures + tolerance report
- [ ] `results/REPRODUCIBILITY.md`
- [ ] Anomaly adjudication with the manuscript claims map

## E-P6 — Docs, examples, release

Goal: `v1.0.0` release with DOI.

- [ ] Docs site complete (quickstart, contracts, CLI); GitHub Pages publishing
- [ ] Example instance + notebook
- [ ] Tag `v1.0.0` + Zenodo DOI + `CITATION.cff`
