from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from wbi_birds.ingest import OUTPUT_COLUMNS, IngestSpec, ingest_ebd

FIXTURE = Path(__file__).parent / "fixtures" / "ebd" / "sample_ebd.txt"
SUITE = (
    "rebnut",
    "borchi2",
    "gockin",
    "brncre",
    "yerwar",
    "swathr",
    "whtspa",
    "tenwar",
    "yebsap",
)


def _spec(tmp_path: Path, **overrides) -> IngestSpec:
    params = {
        "ebd_path": FIXTURE,
        "out_csv": tmp_path / "derived" / "suite_ebd.csv",
        "species": SUITE,
    }
    params.update(overrides)
    return IngestSpec(**params)


def test_ingest_default_filters(tmp_path: Path) -> None:
    summary = ingest_ebd(_spec(tmp_path))
    assert summary.rows_scanned == 15
    assert summary.rows_kept == 12
    assert summary.per_species["rebnut"] == 2
    assert summary.per_species["borchi2"] == 2
    assert summary.per_species["yebsap"] == 2
    assert summary.per_species["gockin"] == 1

    out = tmp_path / "derived" / "suite_ebd.csv"
    with out.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert tuple(rows[0]) == OUTPUT_COLUMNS
    assert len(rows) == 13

    # X counts map to 0.0; months are within the breeding window; no observer data
    counts = {(row[0], row[2]): row[7] for row in rows[1:]}
    assert counts[("rebnut", "2021-05-20")] == "0.0"
    assert all(5 <= int(row[4]) <= 8 for row in rows[1:])
    text = out.read_text(encoding="utf-8")
    assert "obsr" not in text
    assert "observer" not in text.lower()


def test_ingest_complete_checklists_only(tmp_path: Path) -> None:
    summary = ingest_ebd(_spec(tmp_path, complete_checklists_only=True))
    assert summary.rows_kept == 11  # the non-complete yebsap checklist is dropped


def test_ingest_provenance_sidecar(tmp_path: Path) -> None:
    summary = ingest_ebd(_spec(tmp_path))
    sidecar = tmp_path / "derived" / "suite_ebd.csv.provenance.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["source"] == "sample_ebd.txt"
    assert payload["rows_scanned"] == 15
    assert payload["rows_kept"] == 12
    assert payload["output_sha256"] == summary.output_sha256
    assert payload["filters"]["months"] == [5, 6, 7, 8]


def test_ingest_is_deterministic(tmp_path: Path) -> None:
    first = ingest_ebd(_spec(tmp_path))
    second = ingest_ebd(_spec(tmp_path))
    assert first.output_sha256 == second.output_sha256
    sidecar = tmp_path / "derived" / "suite_ebd.csv.provenance.json"
    assert json.loads(sidecar.read_text())["output_sha256"] == first.output_sha256


def test_ingest_rejects_unknown_species_code(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown species code"):
        ingest_ebd(_spec(tmp_path, species=("rebnut", "notabird")))


def test_ingest_rejects_missing_columns(tmp_path: Path) -> None:
    bad = tmp_path / "bad_ebd.txt"
    bad.write_text("COMMON NAME\tOBSERVATION COUNT\nrebnut\t1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required column"):
        ingest_ebd(_spec(tmp_path, ebd_path=bad))
