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
| E-P2 | Provider declaration + pipeline/matrix specs (this blueprint) — **done, plan-only** |
| E-P3 | `run_node` hooks for `build_model` / `run_scenarios` (+ evidence in CI smoke) |
| E-P4 | `run_node` hooks for `ingest_ebd` / `fit_antifunction` |
| E-P5 | `run_node` hooks for `verify_parity` / `compute_frontiers` / `analyze_frontiers` |

## Alpha caveats (pin: `freshforge>=0.1.0a5,<0.2`)

No caching/checkpointing/parallel/remote execution yet; nodes must be idempotent. FreshForge core
stays domain-neutral — all WBI logic lives in this repo (provider `wbi`). If the alpha surface
changes, update this blueprint and the specs in the same change set. Note: template files only validate
*after* expansion (use `freshforge matrix expand/plan/run`); `matrix expand` has no `--summary` flag in
0.1.0a5. Validated locally 2026-10-11: provider discovered, pipeline `validate` + `plan` green, matrix
expands to 5 cases with 0 diagnostics.
