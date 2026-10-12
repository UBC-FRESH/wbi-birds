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
no CSV/RDS/RData in either `wbi_harvesting-birds` or `wbi-birds-manuscript`). Acquisition
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

## Legacy constraint construction (decoded 2026-10-12 from `spadesws3.py`)

The legacy scenario was built by `_gen_scen_base` in
`modules/spades_ws3/python/spadesws3.py` from `input/targets.csv` (indexed by
`tsa`, `year`; columns `vcut`, `abrn`, `cflw_acut_e`, `cgen_vcut_e`,
`cgen_abrn_e`):

- **Volume-cut band**: `ub = vcut(year) * period_length`,
  `lb = ub * (1 - cgen_vcut_e)` (per period).
- **Area-cut even-flow**: `cflw_e` on `cacut_<tsa>` with `cflw_acut_e` per year
  and the reference period = the last period (the v2 engine's
  `even_flow_epsilon` mirrors this form).
- **Bird row(s)**: `cabrn-thlb<i>_<tsa>` per IFM class `i` with
  `lb = abrn(year) * p_i * period_length * (1 - cgen_abrn_e)` and
  `ub = abrn(year) * p_i * period_length`, where `p_i` is the IFM class's area
  fraction at period 0 -- i.e. the legacy bird metric is an abundance-per-area
  index accumulated over the THLB portion, expressed in bird-years
  (`* period_length`).
- **Objective**: production params use `obj_mode = 'min_harea'`
  (minimize harvested area, `zexpr = '1.'`); `max_hvol` (`totvol * util`,
  util 0.85) is the alternative. The manuscript Results text describes the
  bird-range partition (`cbird0.0` .. `cbird1.0`, 11 evenly spaced scenarios);
  the v2 engine reproduces this via per-period bird floors interpolated
  between the nadir and max feasible series.

**Parity implication**: the legacy bird metric is *not* the same row as the v2
landscape bird row (v2 = full anticipation model over the model landbase;
legacy = per-IFM THLB-scaled index in bird-years). Record the transformation
when the reference archive is exported, and prefer a matched-resolution
legacy re-run for the tolerance comparison.

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
