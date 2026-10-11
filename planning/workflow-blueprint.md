# Workflow Blueprint — FreshForge adoption (E-P2)

Status: adopted 2026-10-11. Specs: `workflows/` (pipeline + per-MU matrix). Provider: `wbi` (entry point `freshforge.providers`), plan-only until execution hooks land.

## Why FreshForge

The paper's reproducibility claim rests on a pipeline that spans many heterogeneous steps
(eBird extract → GLM fits → instance compilation → ws3 model → ε-scenario grid → frontier metrics →
analysis/figures). FreshForge makes that pipeline a **declarative, version-controlled graph** with
typed nodes, provider-owned validation/execution, run records, and evidence manifests — i.e. the
process is the artifact, reviewable and testable, not a chain of scripts.

## Node graph (`workflows/wbi_pipeline.yaml`)

| Node | Provider node type | Consumes | Produces | Key parameters |
|---|---|---|---|---|
| `ingest_ebd` | `wbi.ingest_ebd` | (private EBD/SED store) | `derived_tables` | `species_suite`, `months` |
| `fit_antifunction` | `wbi.fit_antifunction` | `derived_tables` | `coefficients` | `family` |
| `compile_instance` | `wbi.compile_instance` | `coefficients` | `instance_root` | `femic_bundle`, `management_unit` |
| `build_model` | `wbi.build_model` | `instance_root` | `forest_model` | `solver` (highs) |
| `run_scenarios` | `wbi.run_scenarios` | `forest_model` | `scenario_results` | `epsilon_steps`, `mode` |
| `compute_frontiers` | `wbi.compute_frontiers` | `scenario_results` | `frontiers` | — |
| `verify_parity` | `wbi.verify_parity` | `scenario_results` | `parity_report` | — |
| `analyze_frontiers` | `wbi.analyze_frontiers` | `frontiers` | `analysis` | — |

## Data-flow contract (links to `planning/data-contract.md`)

`external/wbi-ebird-data` (private annex store) → engine-derived tables → `bird/coefficients.yaml` →
**per-MU instance** (`inputs/`, `config/`, `bird/`) → ws3 model → `results/` tables → frontier
metrics → figures/claims map. Raw eBird content never leaves the private store; nodes exchange
**derived** products only.

## Composition with femic

**Ownership:** `UBC-FRESH/femic` is the control plane for forest-estate model building/running (incl.
ws3 via `femic.ws3_bridge` — Woodstock CSVs → ws3 section files). The WBI engine owns the
bird/tradeoff/analysis layer and orchestrates.

**Target graph per MU:** `wbi.ingest_ebd` → `wbi.fit_antifunction` →
`femic.model_build.{inventory, source_preflight, typed_compile_emit, dataset_lint_import, structural_verify, package_evidence}`
→ `wbi.run_scenarios` → `wbi.compute_frontiers` → `wbi.verify_parity` / `wbi.analyze_frontiers`.

**Interim:** while femic's model-build execution hooks land, the WBI nodes `compile_instance` /
`build_model` act as adapters delegating to femic's CLI/API; they are replaced by direct femic stage
references once executable. AOI model-build dependency: `UBC-FRESH/femic#316` (duplicate-tracking:
engine #8).

## Run matrices

`workflows/wbi_mu_matrix.yaml` expands `workflows/wbi_pipeline_template.yaml` across the five
management units (one instance per MU — the TSR decision-space unit). Later axes (species,
uncertainty draws) get added as matrix axes or nested per-MU campaign configs, not as bespoke scripts.
MU display names: filled from the TSR registry once verified (E-P2 TODO).

## Run records and evidence

- `freshforge run <workflow> --workdir . --namespace <case> --evidence results/workflow/<case>.json`
  writes a durable **evidence manifest** (FreshForge version, spec path, status, summary, full run
  record, diagnostics). These manifests are the project's run records.
- Node artifacts resolve under the run namespace — repeated runs never collide.
- Failed runs still write evidence; audit trail preserved.

## Adoption map (engine phases)

| Phase | Work |
|---|---|
| E-P2 | Provider declaration + pipeline/matrix specs (this blueprint) — **done, plan-only**; AOI model-build dependency registered (`UBC-FRESH/femic#316`) |
| E-P3 | ✅ complete: hooks for `compile_instance` (femic-bundle adapter) / `build_model` / `run_scenarios` + evidence smokes + B3 comparison (2026-10-11) |
| E-P4 | ✅ complete: hooks for `ingest_ebd` / `fit_antifunction`; full five-node chain smoke (ingest → fit → compile → model → bird scenario) with evidence |
| E-P5 | ⏳ `wbi_birds.parity` + `wbi.verify_parity` hook complete (tolerance policy, reports, strict gating); real legacy parity + reproducibility doc pending (`femic#316` / eBird extract) |

## Self-bootstrapping requirement

A user in a fresh environment must reproduce the project from the README alone, via two data lanes:

- **public lane:** released derived inputs snapshot (Zenodo DOI at release) — no private access;
- **team lane:** private annex data (`external/wbi-ebird-data`, DataLad) for the raw-eBird runs.

Bootstrap = pinned installs (engine + femic + ws3 + freshforge) → data lane → `freshforge run` per
management unit (evidence manifests as run records). Acceptance test at E-P6: README-only
reproduction of the headline results through the public lane.

## Alpha caveats (pin: `freshforge @ 5bce95b` until the next PyPI alpha — evidence manifests are unreleased past 0.1.0a5)

No caching/checkpointing/parallel/remote execution yet; nodes must be idempotent. FreshForge core
stays domain-neutral — all WBI logic lives in this repo (provider `wbi`). If the alpha surface
changes, update this blueprint and the specs in the same change set. Note: template files only validate
*after* expansion (use `freshforge matrix expand/plan/run`); `matrix expand` has no `--summary` flag in
0.1.0a5. Validated locally 2026-10-11: provider discovered, pipeline `validate` + `plan` green, matrix
expands to 5 cases with 0 diagnostics.
