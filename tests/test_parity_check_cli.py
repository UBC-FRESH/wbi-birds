from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "parity_check.py"


def _write_engine(instance: Path) -> Path:
    path = instance / "results" / "scenarios" / "tsa24" / "tsa24-s00.csv"
    path.parent.mkdir(parents=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("period", "harvest_volume_m3", "bird_abundance"))
        writer.writerows([(1, 100.0, 10.0), (2, 120.0, 11.0), (3, 140.0, 12.0)])
    return path


def _write_reference(path: Path, scale: float) -> Path:
    rows = []
    for period, harvest, birds in ((1, 100.0, 10.0), (2, 120.0, 11.0), (3, 140.0, 12.0)):
        rows.append(("TSA24", "tsa24-s00", "harvest_volume_m3", period, harvest * scale))
        rows.append(("TSA24", "tsa24-s00", "bird_abundance", period, birds * scale))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("management_unit", "scenario_id", "metric", "period", "value"))
        writer.writerows(rows)
    return path


def _run(instance: Path, reference: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(instance), str(reference), *extra],
        capture_output=True,
        text=True,
        cwd=str(instance.parent),
    )


def test_cli_within_tolerance_strict_passes(tmp_path: Path) -> None:
    instance = tmp_path / "instance"
    _write_engine(instance)
    reference = _write_reference(tmp_path / "reference.csv", scale=1.0002)

    proc = _run(instance, reference, "--label", "tsa24-suite", "--strict")
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "failed=0" in proc.stdout
    assert "strict mode" not in proc.stdout

    parity_dir = instance / "results" / "parity"
    assert (parity_dir / "tsa24-suite-parity.json").is_file()
    assert (parity_dir / "tsa24-suite-parity.md").is_file()


def test_cli_strict_fails_on_mismatch_and_non_strict_passes(tmp_path: Path) -> None:
    instance = tmp_path / "instance"
    _write_engine(instance)
    reference = _write_reference(tmp_path / "reference.csv", scale=1.5)

    strict = _run(instance, reference, "--label", "tsa24-suite", "--strict")
    assert strict.returncode == 1
    assert "strict mode: parity failures present" in strict.stdout

    loose = _run(instance, reference, "--label", "tsa24-suite")
    assert loose.returncode == 0
    assert "failed=6" in loose.stdout
