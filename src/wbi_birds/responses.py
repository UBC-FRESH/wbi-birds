"""Bird response tables: precomputed per-(development type, age) abundance.

The LP bird row is a fixed coefficient per ``(development type, age)`` pair.
The engine therefore does not require the ecological response to be linear in
its covariates: any fitted model can be evaluated once onto the planning state
space and stored as a response table. Resolution order in
:mod:`wbi_birds.bird` is ``response_table`` first, else ``coefficients``.

This module is intentionally dependency-light (stdlib only) so instance
validation can use it without importing ``ws3``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DT_SEP = "|"
RESPONSE_TABLE_RELPATH = Path("bird") / "response_table.csv"
RESPONSE_TABLE_COLUMNS = (
    "species_code",
    "development_type",
    "age",
    "bird_value",
    "bird_value_sd",
)
REQUIRED_RESPONSE_COLUMNS = ("species_code", "development_type", "age", "bird_value")


class ResponseTableError(ValueError):
    """Raised when a response table is missing, malformed, or incomplete."""


def dtype_key_to_str(dtype_key: Iterable[str]) -> str:
    """Canonical string form of a ws3 development-type key."""
    return DT_SEP.join(str(part) for part in dtype_key)


def str_to_dtype_key(value: str) -> tuple[str, ...]:
    """Inverse of :func:`dtype_key_to_str`."""
    return tuple(value.split(DT_SEP))


@dataclass(frozen=True)
class ResponseTable:
    """Per-species abundance response evaluated on the planning state space."""

    species_code: str
    values: Mapping[tuple[tuple[str, ...], int], float]
    sd: Mapping[tuple[tuple[str, ...], int], float] = field(default_factory=dict)
    source: Mapping[str, Any] = field(default_factory=dict)

    def has(self, dtype_key: Sequence[str], age: int) -> bool:
        """Whether the table covers ``(dtype_key, age)``."""
        return (tuple(dtype_key), int(age)) in self.values

    def unit_value(self, dtype_key: Sequence[str], age: int) -> float:
        """Expected per-hectare abundance for one development type and age."""
        key = (tuple(dtype_key), int(age))
        try:
            return float(self.values[key])
        except KeyError as exc:
            joined = dtype_key_to_str(dtype_key)
            raise ResponseTableError(
                f"No response value for species '{self.species_code}' at "
                f"development type '{joined}' age {age}."
            ) from exc

    def unit_sd(self, dtype_key: Sequence[str], age: int) -> float | None:
        """Per-state response standard deviation, when available."""
        return self.sd.get((tuple(dtype_key), int(age)))

    def to_rows(self) -> list[dict[str, Any]]:
        """Deterministically ordered long-format rows for CSV writing."""
        rows: list[dict[str, Any]] = []
        for dtype_key, age in sorted(self.values, key=lambda item: (item[0], item[1])):
            row: dict[str, Any] = {
                "species_code": self.species_code,
                "development_type": dtype_key_to_str(dtype_key),
                "age": int(age),
                "bird_value": float(self.values[(dtype_key, age)]),
                "bird_value_sd": "",
            }
            sd_value = self.sd.get((dtype_key, age))
            if sd_value is not None:
                row["bird_value_sd"] = float(sd_value)
            rows.append(row)
        return rows


def _provenance_path(path: Path) -> Path:
    return path.with_name(path.name + ".provenance.json")


def read_response_tables(path: Path | str) -> dict[str, ResponseTable]:
    """Read all species from a ``response_table.csv``, sorted into per-species tables."""
    source_path = Path(path)
    if not source_path.is_file():
        raise ResponseTableError(f"Response table not found: {source_path}")
    provenance: dict[str, Any] = {}
    provenance_file = _provenance_path(source_path)
    if provenance_file.is_file():
        try:
            loaded = json.loads(provenance_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                provenance = loaded.get("species") or {}
        except (OSError, json.JSONDecodeError):
            provenance = {}

    grouped: dict[str, dict[str, Any]] = {}
    with source_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [column for column in REQUIRED_RESPONSE_COLUMNS if column not in fieldnames]
        if missing:
            raise ResponseTableError(
                f"Response table missing required column(s): {', '.join(missing)}"
            )
        for row in reader:
            code = (row.get("species_code") or "").strip()
            if not code:
                raise ResponseTableError("Response table row has an empty species_code.")
            dtype_key = str_to_dtype_key((row.get("development_type") or "").strip())
            if not any(dtype_key):
                raise ResponseTableError("Response table row has an empty development_type.")
            try:
                age = int(str(row.get("age")).strip())
            except (TypeError, ValueError) as exc:
                raise ResponseTableError(
                    f"Response table row has a non-integer age: {row.get('age')!r}"
                ) from exc
            try:
                value = float(str(row.get("bird_value")).strip())
            except (TypeError, ValueError) as exc:
                raise ResponseTableError(
                    f"Response table row has a non-numeric bird_value: {row.get('bird_value')!r}"
                ) from exc
            raw_sd = (row.get("bird_value_sd") or "").strip()
            sd_value: float | None
            try:
                sd_value = float(raw_sd) if raw_sd else None
            except ValueError as exc:
                raise ResponseTableError(
                    f"Response table row has a non-numeric bird_value_sd: {raw_sd!r}"
                ) from exc

            bucket = grouped.setdefault(code, {"values": {}, "sd": {}})
            bucket["values"][(dtype_key, age)] = value
            if sd_value is not None:
                bucket["sd"][(dtype_key, age)] = sd_value

    if not grouped:
        raise ResponseTableError(f"Response table has no data rows: {source_path}")

    return {
        code: ResponseTable(
            species_code=code,
            values=dict(bucket["values"]),
            sd=dict(bucket["sd"]),
            source=dict((provenance.get(code) or {}).get("source") or {}),
        )
        for code, bucket in grouped.items()
    }


def load_response_table(instance_root: Path | str, species_code: str) -> ResponseTable:
    """Load one species' response table from an instance root."""
    path = Path(instance_root) / RESPONSE_TABLE_RELPATH
    tables = read_response_tables(path)
    if species_code not in tables:
        raise ResponseTableError(
            f"No response table for species '{species_code}' in {path} "
            f"(available: {', '.join(sorted(tables))})."
        )
    return tables[species_code]


def write_response_tables(path: Path | str, tables: Iterable[ResponseTable]) -> Path:
    """Write one or more species' tables to CSV plus a provenance sidecar."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(tables, key=lambda table: table.species_code)
    rows: list[dict[str, Any]] = []
    species_provenance: dict[str, Any] = {}
    for table in ordered:
        table_rows = table.to_rows()
        rows.extend(table_rows)
        species_provenance[table.species_code] = {
            "rows": len(table_rows),
            "source": dict(table.source),
        }

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RESPONSE_TABLE_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    sidecar = {
        "columns": list(RESPONSE_TABLE_COLUMNS),
        "sha256": digest,
        "species": species_provenance,
    }
    _provenance_path(out_path).write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out_path


def merge_response_table(instance_root: Path | str, table: ResponseTable) -> Path:
    """Merge one species' table into an instance's response table, preserving others."""
    path = Path(instance_root) / RESPONSE_TABLE_RELPATH
    tables: dict[str, ResponseTable] = {}
    if path.is_file():
        tables = read_response_tables(path)
    tables[table.species_code] = table
    return write_response_tables(path, tables.values())
