"""Result tables + record writer (E-P3.3).

Writes per-scenario output under a results root:

- ``scenarios/<management-unit>/<scenario-id>.csv`` — per-period table
  (``period, harvest_volume_m3, bird_abundance``)
- ``scenarios/<management-unit>/<scenario-id>.result.yaml`` — the
  ``ScenarioResult`` record, referencing its artifacts

Deterministic: identical inputs produce byte-identical outputs.
"""

from __future__ import annotations

import csv
from pathlib import Path

from wbi_birds.scenarios import ScenarioResult, dump_yaml, load_yaml

TABLE_COLUMNS = ("period", "harvest_volume_m3", "bird_abundance")


def write_scenario_result(
    result: ScenarioResult,
    results_root: Path | str,
    *,
    namespace: str | None = None,
) -> ScenarioResult:
    """Write a scenario result table + record; returns the result with artifacts set.

    ``namespace`` defaults to the lowercased management unit.
    """
    root = Path(results_root)
    ns = namespace or result.management_unit.lower()
    target = root / "scenarios" / ns
    target.mkdir(parents=True, exist_ok=True)
    table_path = target / f"{result.scenario_id}.csv"
    record_path = target / f"{result.scenario_id}.result.yaml"

    with table_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(TABLE_COLUMNS)
        for period, harvest, birds in zip(
            range(1, len(result.harvest_volume_m3_by_period) + 1),
            result.harvest_volume_m3_by_period,
            result.bird_abundance_by_period,
            strict=False,
        ):
            writer.writerow([period, f"{harvest:.6f}", f"{birds:.6f}"])

    updated = result.model_copy(
        update={
            "artifacts": {
                **result.artifacts,
                "table": str(table_path.relative_to(root)),
                "record": str(record_path.relative_to(root)),
            }
        }
    )
    record_path.write_text(dump_yaml(updated), encoding="utf-8")
    return updated


def load_scenario_result(path: Path | str) -> ScenarioResult:
    """Load a ``ScenarioResult`` record from YAML."""
    data = load_yaml(Path(path).read_text(encoding="utf-8"), ScenarioResult)
    assert isinstance(data, ScenarioResult)
    return data
