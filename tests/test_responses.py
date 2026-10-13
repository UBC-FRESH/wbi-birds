from __future__ import annotations

from pathlib import Path

import pytest

from wbi_birds.responses import (
    ResponseTable,
    ResponseTableError,
    dtype_key_to_str,
    merge_response_table,
    read_response_tables,
    str_to_dtype_key,
    write_response_tables,
)

DT = ("tsa24_clipped", "0", "2401000", "100", "2401000")


def _table(code: str = "rebnut", base: float = 1.0) -> ResponseTable:
    return ResponseTable(
        species_code=code,
        values={(DT, 40): base + 40, (DT, 80): base + 80},
        sd={(DT, 40): 0.1, (DT, 80): 0.2},
        source={"fit": "test"},
    )


def _path(tmp_path: Path) -> Path:
    return tmp_path / "bird" / "response_table.csv"


def test_dtype_key_round_trip() -> None:
    assert str_to_dtype_key(dtype_key_to_str(DT)) == DT


def test_write_read_round_trip(tmp_path: Path) -> None:
    path = _path(tmp_path)
    write_response_tables(path, [_table()])
    table = read_response_tables(path)["rebnut"]
    assert table.unit_value(DT, 80) == 81.0
    assert table.unit_sd(DT, 80) == 0.2
    assert table.has(DT, 40)
    assert not table.has(DT, 41)
    # provenance sidecar survives the round trip
    assert table.source == {"fit": "test"}


def test_missing_state_raises(tmp_path: Path) -> None:
    path = _path(tmp_path)
    write_response_tables(path, [_table()])
    table = read_response_tables(path)["rebnut"]
    with pytest.raises(ResponseTableError, match="No response value"):
        table.unit_value(DT, 999)


def test_malformed_table_missing_column(tmp_path: Path) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("species_code,development_type,age\nrebnut,dt|0,80\n", encoding="utf-8")
    with pytest.raises(ResponseTableError, match="missing required column"):
        read_response_tables(path)


def test_malformed_table_bad_age(tmp_path: Path) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "species_code,development_type,age,bird_value\nrebnut,dt|0,not-an-int,1.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ResponseTableError, match="non-integer age"):
        read_response_tables(path)


def test_merge_preserves_other_species(tmp_path: Path) -> None:
    path = _path(tmp_path)
    write_response_tables(path, [_table("rebnut"), _table("borchi2")])
    merge_response_table(tmp_path, _table("gockin"))
    assert set(read_response_tables(path)) == {"rebnut", "borchi2", "gockin"}


def test_read_rejects_non_finite_values(tmp_path: Path) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "species_code,development_type,age,bird_value\nrebnut,dt|0,80,nan\n", encoding="utf-8"
    )
    with pytest.raises(ResponseTableError, match="non-finite bird_value"):
        read_response_tables(path)


def test_read_rejects_stale_sidecar(tmp_path: Path) -> None:
    path = _path(tmp_path)
    write_response_tables(path, [_table()])
    path.write_text(path.read_text(encoding="utf-8").replace("81.0", "99.0"), encoding="utf-8")
    with pytest.raises(ResponseTableError, match="does not match its provenance sidecar"):
        read_response_tables(path)
