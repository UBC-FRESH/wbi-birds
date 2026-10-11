# Instance & Data Contract — v0.1 (DRAFT)

Status: **draft for review** (E-P2.1 / #7). The femic → inputs mapping is fixed in E-P2.2 (#8); schemas are implemented in E-P2.3 (#9).

## Principles

1. **Self-contained instance** — the engine reads only the instance root plus the public `ws3` API; nothing else.
2. **Raw eBird data never enter an instance** (Data Access Terms of Use): fitted coefficients and *derived* tables only.
3. **Provenance-first** — every instance carries a manifest with versions and checksums.
4. **Determinism** — same instance + same engine version → same results; every result set carries its run metadata.

## Layout

```
<instance-root>/  # one instance = one management unit (TSA)
  manifest.yaml            # provenance + versions + checksums (required)
  config/
    run.yaml               # run configuration (TSAs, horizon, even-flow epsilon, utilization, solver)
    species.yaml           # species + guild registry for this instance
  inputs/                  # forest-estate artifact set (femic-derived; mapping fixed in E-P2.2)
  bird/
    coefficients.yaml      # fitted anticipation-function coefficients per species (provenance-stamped)
    derived/               # optional shareable derived tables (no observer identifiers)
  results/                 # engine outputs (scenario runs, frontiers); written by the engine
    scratch/               # ignored working area
```

## Anticipation row (`bird`)

- Coefficients live in `bird/coefficients.yaml` (`species: {code: {swvol, hwvol, age, intercept}}`); legacy WBI naming (`birdaf_*_coeff`).
- The engine evaluates the row per development type: `bird(age) = c1*swdvol(age) + c2*hwdvol(age) + c3*age + c4` (area-weighted in LP coefficients). It is **not** a ws3 complex yield — ws3 resolvers cannot nest calls, and the engine also needs the row to cover runtime-created development types.
- Derived tables: `wbi_birds.ingest` streams the private EBD extract into derived CSVs + provenance sidecars (suite/months/complete-checklist filters; observer identifiers dropped).
- Fitting: `provided` (R-lineage coefficients staged + validated) or engine-native `poisson` MLE (`wbi_birds.fit`); both merge into `bird/coefficients.yaml` with a `source.fit` marker.
- Canonical suite: nine species across four guilds (`wbi_birds.registry`); codes and common names are checked against the eBird taxonomy snapshot (`wbi_birds.taxonomy`).
- `measure_scope`: `harvest` (default) or `landscape` (row sums over `null` + `harvest` prescriptions). Bird scenarios materialize the row on every period (sentinel bounds where unconstrained) and record the per-period series **exactly from the LP solution**.

## Parity comparison

Legacy outputs are compared as long-format reference tables (`management_unit, scenario_id, metric, period, value`) via `wbi_birds.parity`; tolerance policy = `|engine - reference| <= abs_tol + rel_tol * |reference|` (defaults per metric; final values adjudicated in E-P5.3). Reports land under `results/parity/`.

## Results layout

`results/scenarios/<management-unit>/<scenario-id>.csv` — per-period table
(`period, harvest_volume_m3, bird_abundance`); `results/scenarios/<management-unit>/<scenario-id>.result.yaml`
— the `ScenarioResult` record, referencing its artifacts.

## `manifest.yaml` (sketch)

```yaml
schema_version: 1
instance_id: wbi-tsa08
created: 2026-10-11
provenance:
  femic: {commit: "...", outputs_sha256: "..."}
  ws3: {version: "..."}
  ebird: {release: "ebd_rel<Mon>-<Year>", note: "raw private; derived only"}
  bird_model: {commit: "...", fitted: "2026-..."}
  engine: {version: "0.1.0a1"}
checksums:
  algorithm: sha256
  files: {inputs/...: "..."}
```

## `config/run.yaml` (sketch)

```yaml
management_unit: {id: TSA40, name: "Fort St John"}
horizon_years: 80
model: {base_year: 2020, period_length_years: 5, max_age: 1000, harvest_acodes: [harvest]}
even_flow: {epsilon: 0.10}
utilization: 0.85
scenarios: {epsilon_steps: 11, mode: frontier}
solver: {backend: tbd, options: {}}
```

## `config/species.yaml` (sketch)

```yaml
species:
  - {code: rebnut, common: Red-breasted Nuthatch, guild: mature_conifer}
  - {code: borchi2, common: Boreal Chickadee, guild: mature_conifer}
  # ... suite per planning/species-selection.md in the manuscript repo
guilds: [mature_conifer, mixedwood, early_seral, cavity]
```

## `bird/coefficients.yaml` (sketch)

```yaml
source: {ebd_release: "ebd_rel...", fit_script: "...", fitted_on: "2026-..."}
species:
  rebnut: {intercept: 0.0, swvol: 0.0, hwvol: 0.0, age: 0.0}
```

## Validation rules (E-P2.1 validator)

- manifest + required configs present and schema-valid
- referenced files exist; checksums match when present
- species codes ↔ coefficients keys consistent; guilds defined
- **scan rejects** raw eBird files and observer identifiers (Data ToU boundary)
- `results/` writable; `results/scratch/` ignored by checks
- engine version vs manifest pin: warn (not fail) until release policy lands

## Boundaries

- femic is the control plane for forest-estate model building/running (WS → ws3 sections via `femic.ws3_bridge`); the engine composes femic FreshForge providers/outputs. No femic imports in engine runtime; coupling = providers + file contracts (E-P2.2; `UBC-FRESH/femic#316`)
- eBird: raw data stays outside all instances; only coefficients/derived products inside
- ws3: public API only

## Resolved decisions (2026-10-11)

1. **Solver** — default **HiGHS** (open; keeps the reproducibility bundle fully open). Gurobi is a documented switch if HiGHS performance becomes a bottleneck; every result set records solver backend + version in run metadata. Parity implications tracked in E-P5.
2. **Granularity** — **one instance per management unit (TSA)**. The TSR/AAC determination process operates per management unit; aggregating units has no management decision-space analogue. Campaign = five instances.
3. **Coefficient registry** — instance-local copies (as drafted), sourced from the private data store's fit outputs.

## Private raw-data store

- `external/wbi-ebird-data` — private DataLad + git-annex dataset (`UBC-FRESH/wbi-ebird-data`) holding raw EBD/SED and private derived tables. Never public; CI does not initialize submodules; the engine reads derived products only.
