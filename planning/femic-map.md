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

## Open questions (for femic#316)

1. Which artifact set ships per MU — bundle tables, ws3 sections, or both?
2. Where do the five MU instances live: femic-style `external/` overlays, or the engine repo's
   `instances/` directory?
3. Does femic export manifest fragments/checksums the engine can ingest directly?

## Verification

`tests/test_mapping.py`: bundle loads, staging produces `inputs/ws3/*` and the instance validator
stays green; missing/empty sections are rejected.
