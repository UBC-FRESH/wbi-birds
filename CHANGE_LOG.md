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

## 2026-10-11 — E-P6 activated; E-P6.1 docs site

- E-P6 children: #26 (docs), #27 (example + notebook), #28 (release); branch `feature/issue-6-ep6-release`.
- Docs site: quickstart, concepts, workflows, parity, CLI, reproducibility, API reference (autodoc; freshforge mocked); `sphinx-build -W` green; GitHub Pages enabled (`build_type: workflow`).
- Manuscript repo renamed to `UBC-FRESH/wbi-birds-manuscript` (references updated across both repos).

## 2026-10-11 — E-P6.2 example instance + notebook

- `examples/`: packaged fixture estate, ws3 sections, EBD sample, provided coefficients, packaged parity reference; `quickstart.ipynb` walks ingest -> fit -> compile -> build -> scenario -> parity and is executed by the CI `examples` job.
- `workflows/wbi_example.yaml` (six-node graph); `examples` extra (nbconvert/ipykernel/matplotlib); docs page + examples README.
- Hardened machine-readable FreshForge invocations against `FORCE_COLOR`/`CLICOLOR_FORCE` (Rich forces ANSI colour whenever they are present, breaking `json.loads`); upstream report filed at `UBC-FRESH/freshforge#119`.
- Suite: 79 tests green; notebook executes end-to-end (5/5 cells).

## 2026-10-11 — E-P6.3 v1.0.0 release

- Version 1.0.0 (pyproject, `__version__`, provider metadata; version-coherence test reads pyproject); `CITATION.cff` (date-released) + `.zenodo.json`; release workflow now creates the GitHub release with dist assets.
- README rewritten into public lane (fixture bootstrap, acceptance-tested) + campaign lane; `results/REPRODUCIBILITY.md` finalized with the acceptance record.
- Self-bootstrapping acceptance on a fresh clone: clean install -> 79 tests passed -> example notebook 5/5 cells, parity 32/32 (ws3 1.1.0a5, FreshForge 0.1.0a5, HiGHS 1.15.1).
- Zenodo DOI deposit pending enabling the Zenodo-GitHub integration (#29).

## 2026-10-12 — Five-TSA campaign models live (THLB-filtered, 200y/10y, ε=0.1)

- femic P113.5 landed: `femic export woodstock --thlb-min 50` (THLB-filtered landbase; stands with
  `thlb_raw >= 50`, at full stand area), 200-year horizon × 10-year periods, cc operability 80..400,
  regeneration to age 0 (multi-rotation). Five AOI instances re-exported (woodstock + ws3 sections)
  and re-published to the new Arbutus cloud (`object-arbutus.alliancecan.ca`); fresh-clone
  end-to-end downloads verified.
- Five-TSA baselines (maximize `totvol * 0.85`, even-flow ε = 0.1): TSA24 1,443,341,327 m³ /
  50,616,966 birds; TSA16 482,512,616 / 23,038,597; TSA08 596,831,254 / 6,745,036;
  TSA40 434,793,181 / 8,598,516; TSA41 291,035,361 / 5,066,902. Evidence:
  `femic/external/femic-tsa24-instance/evidence/p113_5_campaign_config_2026-10-12.md`.
- ws3 time-unit contract fixes (femic bridge): `.yld` ages in periods with midpoint collapse; `.trn`
  target proportion in percent (post-treatment age from the action `Y` flag).
- `planning/femic-map.md` updated with the campaign configuration + baselines; bird-floor frontier
  sweep (factors 1.00–1.15 of the ε=0.1 baseline series, periods 2..20) running.

## 2026-10-12 — Five-TSA campaign frontier (bird floors, ε=0.1)

- Bird-floor frontier complete on all five campaign models (floors 1.00–1.15× the ε=0.1 baseline
  per-period bird series, periods 2..20, maximize harvest): TSA24/16 hit a hard bird ceiling
  between +5% and +8% with steep harvest losses (−17..−19% at +4.8%); TSA08/40/41 buy +10–22%
  birds for ≤3% harvest. Scenario CSVs + README published under
  `femic/external/femic-tsa<XX>-instance/evidence/campaign_frontier_2026-10-12/`.

## 2026-10-12 — Legacy scenario design decoded (parity prep)

- `planning/parity-reference-acquisition.md` now records the legacy constraint construction from
  `spadesws3.py` (`targets.csv` vcut/abrn bands, per-IFM THLB bird index in bird-years, cflw
  reference = last period, `min_harea`/`max_hvol` objective modes) plus the parity implication
  (legacy bird metric ≠ v2 landscape row).
- Campaign scenario design aligned to the paper's text: 11 scenarios partitioning the bird range
  from nadir to max (`cbird0.00`..`cbird1.00`); partition sweep running.

## 2026-10-12 — Bird-objective solves (#31)

- `ProblemSpec.flow_expr` (even-flow row expression; defaults to `objective_expr`) and
  `objective_expr="bird"` support (z = total bird abundance along the path, requires
  `bird_coefficients`); clear error when even-flow is requested with a bird objective and no
  `flow_expr`; harvest accounting uses `flow_expr` (falls back to `totvol` for bird objectives).
- Tests: bird-max total >= harvest-objective nadir; missing-flow-expr error. Suite 81 green;
  docs `-W` clean.
- Enables the manuscript's maximum-bird endpoint ("maximizing bird abundance in the objective
  function") for the campaign partition; supersedes the bisection proxy.

## 2026-10-12 — Campaign scripts committed

- `scripts/campaign_birdmax.py` (maximum-bird endpoint), `campaign_partition.py` (11-scenario
  nadir-to-max partition; `--max-series` or bisection fallback), `campaign_sensitivity.py`
  (epsilon/utilization at matched targets), `frontier_analyze.py` (trade-off tables).
- True max-bird endpoint exceeds the bisection proxy by 5-9% (TSA24 +9.2%, TSA16 +5.6%),
  confirming the direct bird-objective solve supersedes the proxy for the campaign partition.

## 2026-10-12 — Campaign partition complete (11 scenarios x 5 TSAs)

- The manuscript's scenario design is executed end-to-end: 11 bird scenarios partitioning the
  nadir-to-max range (max-bird solved directly, #31). Bird ranges +12.2% (TSA16) to +70.2%
  (TSA41); top-scenario harvest losses -11% (TSA08) to -83% (TSA24); even-flow epsilon = 0.1
  costs 10-14% of maximum harvest; utilization is an accounting factor (decisions invariant).
- Evidence published per instance (`evidence/campaign_partition_2026-10-12/`, including
  `*-bmax.csv` + series JSON) to the new Arbutus cloud; `planning/femic-map.md` updated.

## 2026-10-12 — E-P4.5: ensemble response embedding (#33)

- Added `wbi_birds.responses` (stdlib-only): `ResponseTable` + CSV I/O with a provenance
  sidecar (`response_table.csv.provenance.json`, SHA256), `dtype_key` string round-trip, and
  merge-preserving staging.
- `wbi_birds.bird`: `BirdResponse = AnticipationCoefficients | ResponseTable`; `bird_unit_value`
  and `compile_bird_*` dispatch on either form; `load_bird_response` resolves response table
  first; `state_space` (registered DTs) and `reachable_state_space` (dry `add_problem` pass that
  materialises transition/regeneration DTs) + `build_response_table` evaluate **any** fitted
  predictor exactly onto the planning state space — the LP stays linear in prescription variables
  without requiring the response to be linear in covariates.
- `wbi_birds.runner`: `ProblemSpec.bird_coefficients` accepts `ResponseTable`; provenance records
  `bird_response` (species, value count, source).
- `wbi_birds.fit`: `stage_response_table` / `stage_response_table_from_csv`.
- `wbi_birds.instance`: accepts `bird/response_table.csv` **or** `bird/coefficients.yaml` (both
  allowed; response table wins); validates headers/numerics/coverage; codes `bird.missing`,
  `bird.missing_species`, `bird.extra_species`, `response_table.invalid`.
- `wbi_birds.forge`: `fit_antifunction` mode `response`; scenario hook uses `load_bird_response`.
- Tests: new `tests/test_responses.py`; response-table exact-evaluation + scenario + fallback in
  `test_bird.py`; staging in `test_fit.py`; validation accept/reject in `test_instance.py`.
  Full suite 96 passed; `ruff check`/`format` and `sphinx-build -W` green.
- Docs: `docs/concepts.rst`, `planning/data-contract.md`, template `bird/README.md`.

Cross-links: manuscript `planning/bird-model-v2-spec.md` §5/§9/§11; review item M1;
`UBC-FRESH/wbi-birds-manuscript#3`. Issue #33.

## 2026-10-12 — E-P4.6: native Python bird regression (#35)

- Added `wbi_birds.regression`: native port of the R/SpaDES `fitBirdBiomassModel`
  logic — `correct_stand_age` (kNN base-year projection, negatives dropped),
  `scale_species_biomass` / `aggregate_wood_types`, `design_matrix`, Poisson MLE
  with full R-`summary()` statistics (`PoissonFitResult`: coefficients, SEs from
  the analytic Fisher information, z, p, null/residual deviance, log-likelihood,
  AIC, dispersion), `stepwise_aic` (backward/forward/both), and
  `linear_predictor` / `expected_count`.
- Added `wbi_birds.covariates`: optional raster-covariate preparation (lazy
  `rasterio`, `[covariates]` extra) + `build_covariate_rows` (FRI-age override,
  wood-type aggregation, negative-age drop).
- `wbi_birds.fit`: `fit_covariates` (full statistics, optional stepwise);
  `fit_poisson_glm` now delegates to the native module and returns the richer
  `FitResult`; existing staging paths unchanged.
- CLI: `wbi-birds fit poisson` (JSON statistics, `--stepwise`) and
  `wbi-birds fit stage-response`.
- Tests: `tests/test_regression.py`, `tests/test_covariates.py`, `tests/test_cli.py`;
  full suite green. No R/SpaDES/subprocess in the fit path.
- Docs: `docs/concepts.rst`, `planning/data-contract.md`.

Issue #35.
