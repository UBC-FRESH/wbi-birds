from __future__ import annotations

import csv
import json
from pathlib import Path

from wbi_birds.parity import (
    DEFAULT_TOLERANCES,
    Tolerance,
    compare,
    compare_engine_vs_reference,
    long_from_engine,
    write_report,
)


def _engine_csv(tmp_path: Path, periods: int = 16) -> Path:
    path = tmp_path / "engine.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("period", "harvest_volume_m3", "bird_abundance"))
        for period in range(1, periods + 1):
            writer.writerow((period, 100.0 * period, 50.0 + period))
    return path


def _reference_rows(periods: int = 16):
    rows = []
    for period in range(1, periods + 1):
        rows.append(("TSA24", "s00", "harvest_volume_m3", period, 100.0 * period))
        rows.append(("TSA24", "s00", "bird_abundance", period, 50.0 + period))
    return rows


def test_tolerance_accepts() -> None:
    tolerance = Tolerance(abs_tol=1.0, rel_tol=1e-3)
    assert tolerance.accepts(100.0, 100.0)
    assert tolerance.accepts(100.5, 100.0)
    assert tolerance.accepts(101.05, 100.0)
    assert not tolerance.accepts(102.0, 100.0)


def test_compare_matching_within_tolerance(tmp_path: Path) -> None:
    engine = _engine_csv(tmp_path)
    reference = tmp_path / "reference.csv"
    rows = [
        (mu, sid, metric, period, value * 1.0005)  # within 0.1% relative
        for mu, sid, metric, period, value in _reference_rows()
    ]
    with reference.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("management_unit", "scenario_id", "metric", "period", "value"))
        writer.writerows(rows)

    report = compare_engine_vs_reference(
        engine, reference, management_unit="TSA24", scenario_id="s00"
    )
    summary = report.summary()
    assert summary["n_records"] == 32
    assert summary["n_compared"] == 32
    assert summary["n_failed"] == 0
    assert summary["per_metric"]["harvest_volume_m3"]["n"] == 16


def test_compare_flags_tolerance_failure() -> None:
    engine_rows = [("TSA24", "s00", "harvest_volume_m3", 1, 105.0)]
    reference_rows = [("TSA24", "s00", "harvest_volume_m3", 1, 100.0)]
    report = compare(engine_rows, reference_rows)
    record = report.records[0]
    assert not record.passed
    assert record.reason == "tolerance"
    assert record.abs_diff == 5.0
    assert report.summary()["n_failed"] == 1


def test_compare_missing_and_extra_rows() -> None:
    engine_rows = [
        ("TSA24", "s00", "harvest_volume_m3", 1, 100.0),
        ("TSA24", "s00", "harvest_volume_m3", 3, 300.0),  # extra: not in reference
    ]
    reference_rows = [
        ("TSA24", "s00", "harvest_volume_m3", 1, 100.0),
        ("TSA24", "s00", "harvest_volume_m3", 2, 200.0),  # missing in engine
    ]
    report = compare(engine_rows, reference_rows)
    reasons = {record.period: record.reason for record in report.records}
    assert reasons[1] == ""
    assert reasons[2] == "missing_engine"
    assert reasons[3] == "missing_reference"
    assert report.summary()["n_failed"] == 2


def test_long_from_engine(tmp_path: Path) -> None:
    rows = long_from_engine(
        _engine_csv(tmp_path, periods=2), management_unit="TSA24", scenario_id="s00"
    )
    assert len(rows) == 4
    assert rows[0] == ("TSA24", "s00", "harvest_volume_m3", 1, 100.0)
    assert rows[1] == ("TSA24", "s00", "bird_abundance", 1, 51.0)


def test_write_report_deterministic(tmp_path: Path) -> None:
    report = compare(_reference_rows(), _reference_rows())
    artifacts_a = write_report(report, tmp_path / "results-a", label="tsa24")
    artifacts_b = write_report(report, tmp_path / "results-b", label="tsa24")
    assert artifacts_a.keys() == {"json", "markdown"}
    for key in artifacts_a:
        a = (tmp_path / "results-a" / artifacts_a[key]).read_bytes()
        b = (tmp_path / "results-b" / artifacts_b[key]).read_bytes()
        assert a == b
    markdown = (tmp_path / "results-a" / artifacts_a["markdown"]).read_text()
    assert "# Parity report — tsa24" in markdown
    assert "| metric |" in markdown
    payload = json.loads((tmp_path / "results-a" / artifacts_a["json"]).read_text())
    assert payload["summary"]["n_failed"] == 0
    assert len(DEFAULT_TOLERANCES) == 2
