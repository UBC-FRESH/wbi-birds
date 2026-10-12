# femic → Engine Mapping (E-P2.2, v1)

Status: **v1 drafted 2026-10-11.** femic is the control plane for forest-estate model building/running;
this document maps its outputs into the engine instance contract. The final artifact set for
TSA08/16/24/40/41 is decided in [`UBC-FRESH/femic#316`](https://github.com/UBC-FRESH/femic/issues/316).

## Boundary

- **femic:** inventory/yield compilation, model input bundles, Woodstock exports, and
  `femic.ws3_bridge` → ws3 Woodstock section files.
- **engine:** consumes the **file contract** below and stages artifacts into the instance;
  no femic imports.
- **ws3:** loads the section files (engine calls the ws3 public API).

## Contract: engine `inputs/ws3/`

A per-MU instance stores one ws3 model slice as five Woodstock section files:

| File | Contents (per `femic.ws3_bridge` writer) |
|---|---|
| `<model>.lan` | THEME blocks: TSA, managed state, AU, stratum code, yield-curve IDs |
| `<model>.are` | `*A tsa ifm au stratum curve age area_ha` rows |
| `<model>.yld` | `*Y` curve headers plus yields |
| `<model>.act` | actions (`*ACTION`, `*OPERABLE`) |
| `<model>.trn` | transitions (`*CASE`, `*SOURCE`, `*TARGET`) |

Provenance (femic commit + export id + checksums) is recorded in the instance manifest; the checksum
framework is in place and hashes are populated at the first real export.

## Engine-side API (implemented)

- `wbi_birds.mapping.load_ws3_sections(directory, model_name)` — validates presence, non-emptiness,
  and Woodstock shape (`*` records).
- `wbi_birds.mapping.stage_ws3_sections(bundle, instance_root)` — copies the five files into
  `inputs/ws3/` and returns staged relative paths for provenance recording.

## Fixture

`tests/fixtures/femic_ws3_bundle/` holds a real ws3 example model slice (`tsa24_clipped`, copied
from `UBC-FRESH/ws3`; MIT; provenance in the fixture README). It is replaced by a genuine femic
export for one AOI MU when `femic#316` lands.

## Resolved contract (P113, 2026-10-11)

1. **Artifact set per MU**: both — each instance keeps the model-input bundle
   (`data/model_input_bundle/`) and exports Woodstock CSVs (`output/woodstock/`) plus the ws3
   sections (`output/ws3/tsa<code>.{lan,are,yld,act,trn}`); the engine stages the sections only.
2. **Placement**: five public DataLad instance repos under `UBC-FRESH`
   (`femic-tsa08|16|24|40|41-instance`), wired as `external/` submodules of `femic`; the engine
   consumes their exported bundles.
3. **Checksums/manifests**: dataset checksums live in femic `metadata/required_datasets.yaml`;
   per-run provenance is in the instance `runtime/logs/*manifest*.json`; the ws3 handoff is
   delivered by the `femic.ws3_bridge` node (`femic export ws3-sections`).

Graphs: `external/femic-tsa<code>-instance/workflows/freshforge/tsa<code>_model_build_workflow.yaml`
(`validate_case -> geospatial_preflight -> compile_upstream -> btc_post_tipsy -> export_woodstock
-> ws3_bridge`); `freshforge validate` + `plan` green for all five.

## Verification

`tests/test_mapping.py`: bundle loads, staging produces `inputs/ws3/*` and the instance validator
stays green; missing/empty sections are rejected.

## Verified end-to-end (2026-10-12)

The P113.4 smoke executed the full chain on fresh public data and solved a
genuine ε-scenario in this engine: fresh VRI 2025 clip -> VDYP (Wine) ->
TIPSY/BTC (Wine) -> model-input bundle -> Woodstock export (species splits;
cc 80..400; initial-age cap 300 + 10-year snapping) -> `tsa24.{lan,are,yld,act,trn}`
-> `build_model` (54 development types, 132 curves, 16 x 5-year periods) ->
**optimal, harvest 41,899,620.69 m3, birds 59,432,387.76**.
Evidence: `femic/external/femic-tsa24-instance/evidence/p113_4_smoke_2026-10-12.md`.

Note the ws3 Woodstock **time-unit contract**: `.are` ages and `.act` action
timing are in periods (ws3 multiplies by the period length); the bridge handles
the conversion (`--period-length`).
