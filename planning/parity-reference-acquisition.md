# Legacy reference acquisition (E-P5.3)

Real parity (#24) compares engine results against the legacy RBNU / 5-TSA simulation
outputs. This note records where those numbers live, how to turn them into the
reference-table contract, and what still gates the run.

## Reference-table contract

The comparison consumes a long-format CSV:

| management_unit | scenario_id | metric | period | value |
|---|---|---|---|---|
| TSA24 | tsa24-s00 | harvest_volume_m3 | 1 | 123.4 |

- Metric names must match the engine columns (`harvest_volume_m3`, `bird_abundance`;
  extend `wbi_birds.parity.DEFAULT_TOLERANCES` for any additional metric).
- `management_unit` ids follow the phase matrix (`workflows/wbi_mu_matrix.yaml`).
- `scenario_id` follows the engine convention used in
  `<instance>/results/scenarios/<unit-lower>/<scenario>.csv` (e.g. `tsa24-s00`).

## Where the legacy numbers live

The legacy pipeline (`UBC-FRESH/wbi_harvesting-birds`, `01_run-spades.R` + `modules/`)
ran under R / SpaDES 0.1.x and cached its simulation outputs in the original run
environment. **Those outputs are not committed to the repos** (checked 2026-10-11:
no CSV/RDS/RData in either `wbi_harvesting-birds` or `wbi-birds-2021`). Acquisition
options, in order of preference:

1. **Archived outputs** — retrieve the cached simulation outputs (RDS/data cache)
   from the original run environment (owner: GP).
2. **Legacy re-run** — re-run the legacy pipeline from archived inputs and the
   legacy R environment. Usable as the reference only if inputs and scripts are
   unchanged; record the environment (R/ws3 versions) with the archive.

Either way the raw archive is stored in the private data store
(`wbi-ebird-data`) or an equivalent owner-controlled archive — never redistributed.

## Export checklist → reference CSV

1. Map the legacy scenario grid to engine scenario ids (grid definition lives in the
   legacy `modules/`; the engine grid is in `workflows/wbi_pipeline_template.yaml`).
2. Align periods (legacy 16 periods ↔ engine `period` 1..16).
3. Extract per scenario × period:
   - harvest volume total (m³) → `harvest_volume_m3` (record any unit conversion);
   - the legacy bird metric → `bird_abundance`; **verify the legacy definition**
     (abundance index vs biomass, harvest-scope vs landscape-scope) and record the
     transformation. The engine bird row is the landscape-scope anticipation model
     (`planning/data-contract.md` § Anticipation row).
4. Write the CSV, compute its SHA256, and record it with the run in #24.

## Running the comparison

```bash
python scripts/parity_check.py <instance> <reference.csv> --label <mu> [--strict]
```

Reports land in `<instance>/results/parity/`; the FreshForge hook (`wbi.verify_parity`)
does the same inside a workflow run. Default tolerance policy: `|engine - reference| <=
abs_tol + rel_tol * |reference|` with `rel_tol = 1e-3` per metric — final values are
adjudicated here, against the legacy numbers, before any manuscript claim is made.

## Gating

- legacy reference archive (this note),
- engine-side model inputs for the 5 AOI TSAs (`UBC-FRESH/femic#316`),
- eBird extract + coefficients (request submitted; runbook in the manuscript repo).

Tracked in #24; the parent phase (#5) closes with the real parity run.
