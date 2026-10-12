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
genuine scenario in this engine (evidence:
`femic/external/femic-tsa24-instance/evidence/p113_4_smoke_2026-10-12.md`).

The **campaign configuration** (P113.5) then locked: THLB-filtered landbase
(`femic export woodstock --thlb-min 50`; stands with `thlb_raw >= 50`, at full
stand area), 200-year horizon x 10-year periods (20 periods, ~2 rotations),
initial ages capped at 300 + snapped to 10-year midpoints, cc operability
80..400, regeneration to age 0, and even-flow epsilon = 0.1 (symmetric band
anchored to the final period). Five-TSA baselines (maximize `totvol * 0.85`,
no bird floors):

| TSA | dtypes / curves | Harvest (m3) | Birds |
|---|---|---|---|
| 24 | 27 / 132 | 1,443,341,327 | 50,616,966 |
| 16 | 49 / 246 | 482,512,616 | 23,038,597 |
| 08 | 32 / 118 | 596,831,254 | 6,745,036 |
| 40 | 30 / 162 | 434,793,181 | 8,598,516 |
| 41 | 38 / 217 | 291,035,361 | 5,066,902 |

Evidence: `femic/external/femic-tsa24-instance/evidence/p113_5_campaign_config_2026-10-12.md`.

Bird-floor frontier on the same configuration (floors on periods 2..20 as
factors of each TSA's ε=0.1 baseline bird series, maximize harvest): two
regimes — TSA24/16 reach +4.8% birds at −17..−19% harvest with a hard bird
ceiling between +5% and +8%; TSA08/40/41 buy +10..22% birds for ≤3% harvest
loss. Scenario CSVs + README:
`femic/external/femic-tsa<code>-instance/evidence/campaign_frontier_2026-10-12/`.

Note the ws3 Woodstock **time-unit contract**: `.are` stand ages, `.act`
action-timing bounds, and `.yld` curve ages are in periods (ws3 multiplies them
by the period length via `convert_periods_to_years`); `.trn` target rows carry a
**proportion in percent** (not an age), and the post-treatment age comes from
the action's `*ACTION <code> Y` flag (targetage 0). The bridge handles all
conversions (`--period-length`).

## Verified ws3 semantics (2026-10-12, ws3_hint capability)

Confirmed via the ws3 agent capability surface (`ws3_hint`, citations validated
against the installed package + HTTP 200 doc URLs) and against the source:

- **Yield curves extend flat (constant) beyond the last (x, y) data point** --
  `Curve.add_points` appends a terminal point at the curve's `xmax` carrying the
  last value (`ws3/core.py`), so curve length never limits yield prediction for
  stands of any age.
- **`.are` stand ages, `.act` action-timing bounds, and `.yld` curve ages are
  periods** (ws3 multiplies by the model period length; the bridge converts
  years -> periods and collapses yearly `.yld` samples to period midpoints).
- **`.trn` `*TARGET` trailing token is a proportion in percent** (`tprop =
  value * 0.01`); the post-treatment age comes from the action's `Y` flag
  (`*ACTION cc Y` -> targetage 0, regeneration/multi-rotation).
