# `bird/` — species response data

Two response forms are supported. Resolution order is **response table first,
else coefficients**. An instance must carry at least one covering every species
in `config/species.yaml`.

## `coefficients.yaml` (legacy linear path)

```yaml
source: {ebd_release: "...", fit_script: "...", fitted_on: "..."}
species:
  rebnut: {intercept: 0.7594, swvol: 0.002181, hwvol: -0.011763, age: -0.0008235}
```

Applied as `bird(age) = c1*swdvol(age) + c2*hwdvol(age) + c3*age + c4`.
Kept for parity with the legacy R line.

## `response_table.csv` (v2 ensemble path)

```csv
species_code,development_type,age,bird_value,bird_value_sd
rebnut,"stratum|0|AU|1|target",80,12.34,0.41
```

Precomputed values of any fitted response, evaluated once on the planning state
space (`wbi_birds.bird.reachable_state_space`, `build_response_table`).
`development_type` is `"|".join(dtype_key)`. Because the LP row is a fixed
coefficient per (development type, age), the response may be arbitrarily
non-linear and the LP stays linear in the prescription variables.

A provenance sidecar (`response_table.csv.provenance.json`) is written next to
the table and carries the source metadata and SHA256.
