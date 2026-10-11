"""Legacy parity comparison (E-P5.1).

Aligns engine result tables against legacy reference tables (long format:
``management_unit, scenario_id, metric, period, value``), applies per-metric
tolerances (absolute + relative), and emits deterministic comparison records
and reports.

Tolerance policy (defaults; final values adjudicated in E-P5.3):

- ``pass`` when ``|engine - reference| <= abs_tol + rel_tol * |reference|``
- metrics without an explicit tolerance use :data:`DEFAULT_TOLERANCE`
- missing reference rows / extra engine rows are explicit failures with reasons
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ENGINE_METRIC_COLUMNS = {
    "harvest_volume_m3": "harvest_volume_m3",
    "bird_abundance": "bird_abundance",
}


@dataclass(frozen=True)
class Tolerance:
    """Absolute + relative acceptance band."""

    abs_tol: float = 1e-6
    rel_tol: float = 1e-3

    def accepts(self, engine: float, reference: float) -> bool:
        return abs(engine - reference) <= self.abs_tol + self.rel_tol * abs(reference)

    def to_dict(self) -> dict[str, float]:
        return {"abs_tol": self.abs_tol, "rel_tol": self.rel_tol}


DEFAULT_TOLERANCE = Tolerance()
DEFAULT_TOLERANCES: dict[str, Tolerance] = {
    "harvest_volume_m3": Tolerance(abs_tol=1e-6, rel_tol=1e-3),
    "bird_abundance": Tolerance(abs_tol=1e-6, rel_tol=1e-3),
}


@dataclass(frozen=True)
class ComparisonRecord:
    """One (unit, scenario, metric, period) comparison."""

    management_unit: str
    scenario_id: str
    metric: str
    period: int
    engine: float | None
    reference: float | None
    abs_diff: float | None
    rel_diff: float | None
    tolerance: dict[str, float]
    passed: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParityReport:
    """Full comparison outcome."""

    records: tuple[ComparisonRecord, ...]

    def summary(self) -> dict[str, Any]:
        compared = sum(
            1
            for record in self.records
            if record.engine is not None and record.reference is not None
        )
        passed = sum(1 for record in self.records if record.passed)
        failed = len(self.records) - passed
        per_metric: dict[str, dict[str, Any]] = {}
        for record in self.records:
            stats = per_metric.setdefault(
                record.metric,
                {"n": 0, "failed": 0, "max_abs_diff": 0.0, "max_rel_diff": 0.0},
            )
            stats["n"] += 1
            if not record.passed:
                stats["failed"] += 1
            if record.abs_diff is not None:
                stats["max_abs_diff"] = max(stats["max_abs_diff"], abs(record.abs_diff))
            if record.rel_diff is not None:
                stats["max_rel_diff"] = max(stats["max_rel_diff"], abs(record.rel_diff))
        return {
            "n_records": len(self.records),
            "n_compared": compared,
            "n_passed": passed,
            "n_failed": failed,
            "per_metric": {metric: per_metric[metric] for metric in sorted(per_metric)},
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "records": [record.to_dict() for record in self.records],
        }


def long_from_engine(
    csv_path: Path | str,
    *,
    management_unit: str,
    scenario_id: str,
    metric_columns: Mapping[str, str] | None = None,
) -> list[tuple[str, str, str, int, float]]:
    """Read an engine scenario CSV into long-format rows."""
    columns = dict(metric_columns or ENGINE_METRIC_COLUMNS)
    rows: list[tuple[str, str, str, int, float]] = []
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            period = int(row["period"])
            for metric, column in columns.items():
                rows.append((management_unit, scenario_id, metric, period, float(row[column])))
    return rows


def long_from_reference(csv_path: Path | str) -> list[tuple[str, str, str, int, float]]:
    """Read a legacy reference table (long format) into rows."""
    rows: list[tuple[str, str, str, int, float]] = []
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"management_unit", "scenario_id", "metric", "period", "value"}
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            raise ValueError(f"Reference table must have columns {sorted(required)}: {csv_path}")
        for row in reader:
            rows.append(
                (
                    row["management_unit"],
                    row["scenario_id"],
                    row["metric"],
                    int(row["period"]),
                    float(row["value"]),
                )
            )
    return rows


def compare(
    engine_rows: Sequence[tuple[str, str, str, int, float]],
    reference_rows: Sequence[tuple[str, str, str, int, float]],
    *,
    tolerances: Mapping[str, Tolerance] | None = None,
) -> ParityReport:
    """Compare long-format engine rows against reference rows."""
    tolerance_map = dict(tolerances or DEFAULT_TOLERANCES)
    engine_index = {
        (mu, sid, metric, period): value for mu, sid, metric, period, value in engine_rows
    }
    reference_index = {
        (mu, sid, metric, period): value for mu, sid, metric, period, value in reference_rows
    }
    keys = sorted(set(engine_index) | set(reference_index))
    records: list[ComparisonRecord] = []
    for mu, scenario_id, metric, period in keys:
        tolerance = tolerance_map.get(metric, DEFAULT_TOLERANCE)
        engine = engine_index.get((mu, scenario_id, metric, period))
        reference = reference_index.get((mu, scenario_id, metric, period))
        if engine is None:
            records.append(
                ComparisonRecord(
                    management_unit=mu,
                    scenario_id=scenario_id,
                    metric=metric,
                    period=period,
                    engine=None,
                    reference=reference,
                    abs_diff=None,
                    rel_diff=None,
                    tolerance=tolerance.to_dict(),
                    passed=False,
                    reason="missing_engine",
                )
            )
            continue
        if reference is None:
            records.append(
                ComparisonRecord(
                    management_unit=mu,
                    scenario_id=scenario_id,
                    metric=metric,
                    period=period,
                    engine=engine,
                    reference=None,
                    abs_diff=None,
                    rel_diff=None,
                    tolerance=tolerance.to_dict(),
                    passed=False,
                    reason="missing_reference",
                )
            )
            continue
        abs_diff = engine - reference
        rel_diff = abs_diff / abs(reference) if reference != 0.0 else None
        passed = tolerance.accepts(engine, reference)
        records.append(
            ComparisonRecord(
                management_unit=mu,
                scenario_id=scenario_id,
                metric=metric,
                period=period,
                engine=engine,
                reference=reference,
                abs_diff=abs_diff,
                rel_diff=rel_diff,
                tolerance=tolerance.to_dict(),
                passed=passed,
                reason="" if passed else "tolerance",
            )
        )
    return ParityReport(records=tuple(records))


def compare_engine_vs_reference(
    engine_csv: Path | str,
    reference_csv: Path | str,
    *,
    management_unit: str,
    scenario_id: str,
    tolerances: Mapping[str, Tolerance] | None = None,
) -> ParityReport:
    """Convenience wrapper: engine scenario CSV vs long-format reference table."""
    engine_rows = long_from_engine(
        engine_csv, management_unit=management_unit, scenario_id=scenario_id
    )
    reference_rows = long_from_reference(reference_csv)
    return compare(engine_rows, reference_rows, tolerances=tolerances)


def compare_instance_results(
    instance_root: Path | str,
    reference_csv: Path | str,
    *,
    tolerances: Mapping[str, Tolerance] | None = None,
) -> ParityReport:
    """Compare every engine scenario result under an instance against a reference table.

    Engine tables are discovered at ``<instance>/results/scenarios/<unit>/<scenario>.csv``;
    the management unit is derived from the directory name (upper-cased) and the
    scenario id from the file stem.
    """
    root = Path(instance_root)
    results_dir = root / "results" / "scenarios"
    if not results_dir.is_dir():
        raise ValueError(f"No results/scenarios directory under {root}")
    engine_rows: list[tuple[str, str, str, int, float]] = []
    for csv_path in sorted(results_dir.glob("*/*.csv")):
        engine_rows.extend(
            long_from_engine(
                csv_path,
                management_unit=csv_path.parent.name.upper(),
                scenario_id=csv_path.stem,
            )
        )
    if not engine_rows:
        raise ValueError(f"No scenario result tables found under {results_dir}")
    reference_rows = long_from_reference(Path(reference_csv))
    return compare(engine_rows, reference_rows, tolerances=tolerances)


def write_report(report: ParityReport, results_root: Path | str, *, label: str) -> dict[str, str]:
    """Write deterministic JSON + Markdown parity report artifacts."""
    root = Path(results_root) / "parity"
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"{label}-parity.json"
    md_path = root / f"{label}-parity.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = report.summary()
    lines = [
        f"# Parity report — {label}",
        "",
        f"- compared: {summary['n_compared']}",
        f"- passed: {summary['n_passed']}",
        f"- failed: {summary['n_failed']}",
        "",
        "| metric | n | failed | max abs diff | max rel diff |",
        "|---|---|---|---|---|",
    ]
    for metric, stats in summary["per_metric"].items():
        lines.append(
            f"| {metric} | {stats['n']} | {stats['failed']} | "
            f"{stats['max_abs_diff']:.6g} | {stats['max_rel_diff']:.6g} |"
        )
    failures = [record for record in report.records if not record.passed]
    if failures:
        lines.extend(["", f"## Failures ({len(failures)})", ""])
        for record in failures[:50]:
            lines.append(
                f"- {record.management_unit}/{record.scenario_id}/{record.metric}/"
                f"t{record.period}: {record.reason} "
                f"(engine={record.engine}, reference={record.reference})"
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "json": str(json_path.relative_to(Path(results_root))),
        "markdown": str(md_path.relative_to(Path(results_root))),
    }
