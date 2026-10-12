from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from wbi_birds.ingest import (
    OUTPUT_COLUMNS,
    IngestSpec,
    ZeroFillSpec,
    ingest_ebd,
    ingest_ebd_zero_filled,
)

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


def test_ingest_from_zip_archive(tmp_path: Path) -> None:
    import zipfile

    archive = tmp_path / "ebd_sample.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(FIXTURE, arcname="ebd_sample/ebd_sample.txt")
    summary = ingest_ebd(_spec(tmp_path, ebd_path=archive))
    assert summary.rows_kept == 12
    assert summary.source == "ebd_sample.zip"
    assert summary.source_member == "ebd_sample/ebd_sample.txt"
    sidecar = tmp_path / "derived" / "suite_ebd.csv.provenance.json"
    assert json.loads(sidecar.read_text())["source_member"] == "ebd_sample/ebd_sample.txt"


def test_ingest_zip_without_ebd_member_rejected(tmp_path: Path) -> None:
    import zipfile

    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("notes.txt", "not an ebd member")
    with pytest.raises(ValueError, match=r"No 'ebd_\*\.txt' member"):
        ingest_ebd(_spec(tmp_path, ebd_path=archive))


SED_FIXTURE = Path(__file__).parent / "fixtures" / "ebd" / "sample_sed.txt"


def _zero_spec(tmp_path: Path, **overrides) -> ZeroFillSpec:
    params = {
        "ebd_path": FIXTURE,
        "sed_path": SED_FIXTURE,
        "out_csv": tmp_path / "derived" / "suite_zero.csv",
        "species": SUITE,
    }
    params.update(overrides)
    return ZeroFillSpec(**params)


def _zero_rows(tmp_path: Path) -> list[dict[str, str]]:
    out = tmp_path / "derived" / "suite_zero.csv"
    with out.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_zero_fill_grid_and_counts(tmp_path: Path) -> None:
    summary = ingest_ebd_zero_filled(_zero_spec(tmp_path))
    assert summary.checklists == 12  # S005 incomplete, S006 off-season, S013 incidental
    assert summary.rows == 12 * len(SUITE)
    assert sum(summary.per_species_detections.values()) == 10
    assert sum(summary.per_species_non_detections.values()) == 98
    assert summary.per_species_detections["rebnut"] == 2
    assert summary.per_species_detections["yebsap"] == 0
    assert summary.unspecified_counts == 1


def test_zero_fill_x_is_detection_without_count(tmp_path: Path) -> None:
    ingest_ebd_zero_filled(_zero_spec(tmp_path))
    rows = {(r["checklist_id"], r["species_code"]): r for r in _zero_rows(tmp_path)}
    observed = rows[("S004", "rebnut")]
    assert observed["detection"] == "1"
    assert observed["observation_count"] == ""  # X -> unspecified, not 0
    absent = rows[("S004", "borchi2")]
    assert absent["detection"] == "0"
    assert absent["observation_count"] == "0"


def test_zero_fill_filters_events_and_drops_observers(tmp_path: Path) -> None:
    summary = ingest_ebd_zero_filled(_zero_spec(tmp_path))
    out = tmp_path / "derived" / "suite_zero.csv"
    text = out.read_text(encoding="utf-8")
    assert "obsr" not in text.lower()
    checklist_ids = {r["checklist_id"] for r in _zero_rows(tmp_path)}
    assert checklist_ids.isdisjoint({"S005", "S006", "S013"})
    assert summary.filters["protocols"] == ["Stationary", "Traveling"]


def test_zero_fill_carries_effort(tmp_path: Path) -> None:
    ingest_ebd_zero_filled(_zero_spec(tmp_path))
    rows = {(r["checklist_id"], r["species_code"]): r for r in _zero_rows(tmp_path)}
    event = rows[("S002", "rebnut")]
    assert event["protocol_type"] == "Traveling"
    assert event["duration_minutes"] == "60"
    assert event["effort_distance_km"] == "1.5"
    assert event["number_observers"] == "2"


def test_zero_fill_provenance_sidecar(tmp_path: Path) -> None:
    summary = ingest_ebd_zero_filled(_zero_spec(tmp_path))
    sidecar = tmp_path / "derived" / "suite_zero.csv.provenance.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["source_sed"] == "sample_sed.txt"
    assert payload["checklists"] == 12
    assert payload["per_species_detections"]["borchi2"] == 2
    assert payload["unspecified_counts"] == 1
    assert payload["output_sha256"] == summary.output_sha256


def test_zero_fill_requires_checklist_column(tmp_path: Path) -> None:
    bad = tmp_path / "bad_ebd.txt"
    bad.write_text(
        "COMMON NAME\tSCIENTIFIC NAME\tOBSERVATION COUNT\tLATITUDE\tLONGITUDE"
        "\tOBSERVATION DATE\nrebnut\tSitta canadensis\t1\t56\t-120\t2021-06-01\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="SAMPLING EVENT IDENTIFIER"):
        ingest_ebd_zero_filled(_zero_spec(tmp_path, ebd_path=bad))
