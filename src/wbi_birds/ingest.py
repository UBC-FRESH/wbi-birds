"""EBD-derived ingestion (E-P4.3).

Streams the private eBird Basic Dataset extract (tab-delimited, as received)
into a derived point-level table filtered to the species suite and breeding
months, with a provenance sidecar. **Raw content never leaves the private
store** — the engine emits derived products only, and observer identifiers are
never carried into the output.

Legacy-compatible convention: observation count ``X`` maps to ``0.0``.

Accepts either an EBD ``.txt`` file or a ``.zip`` archive containing one
(selects the largest ``ebd_*.txt`` member).

For the v2 campaign, :func:`ingest_ebd_zero_filled` joins the EBD to the eBird
**Sampling Event Data** and emits a complete ``checklist x species``
grid (detections and non-detections) with effort fields.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from wbi_birds.taxonomy import TAXONOMY_SNAPSHOT

OUTPUT_COLUMNS = (
    "species_code",
    "scientific_name",
    "observation_date",
    "year",
    "month",
    "latitude",
    "longitude",
    "observation_count",
)

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "common_name": ("common name", "comname", "common"),
    "scientific_name": ("scientific name", "sciname", "scientific"),
    "observation_count": ("observation count", "observationcounts", "count"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng"),
    "observation_date": ("observation date", "date"),
    "checklist_id": ("sampling event identifier", "samplingeventidentifier"),
    "all_species_reported": ("all species reported",),
}

REQUIRED_COLUMNS = (
    "common_name",
    "scientific_name",
    "observation_count",
    "latitude",
    "longitude",
    "observation_date",
)

TRUE_FLAGS = {"1", "true", "yes", "y"}


@dataclass(frozen=True)
class IngestSpec:
    """Ingestion request for one derived table."""

    ebd_path: Path
    out_csv: Path
    species: tuple[str, ...]
    months: tuple[int, ...] = (5, 6, 7, 8)
    complete_checklists_only: bool = False


@dataclass(frozen=True)
class IngestSummary:
    """Provenance summary for a derived table."""

    source: str
    source_size_bytes: int
    output: str
    output_sha256: str
    filters: dict[str, Any]
    rows_scanned: int
    rows_kept: int
    per_species: dict[str, int]
    source_member: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())


def _resolve_columns(
    header: list[str],
    aliases: dict[str, tuple[str, ...]] = COLUMN_ALIASES,
    required: tuple[str, ...] = REQUIRED_COLUMNS,
) -> dict[str, int]:
    normalized = [_normalize(name) for name in header]
    index: dict[str, int] = {}
    for field, field_aliases in aliases.items():
        for alias in field_aliases:
            if alias in normalized:
                index[field] = normalized.index(alias)
                break
    missing = [field for field in required if field not in index]
    if missing:
        raise ValueError(
            f"File is missing required column(s): {', '.join(missing)} (header: {header!r})"
        )
    return index


@contextmanager
def _open_text_member(path: Path, tag: str) -> Iterator[tuple[Any, str]]:
    """Yield (text stream, member name) for a delimited file or a ``.zip`` member."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".txt") and tag in Path(name).name.lower()
            ]
            if not members:
                raise ValueError(f"No '{tag}*.txt' member found in archive: {path}")
            member = max(members, key=lambda name: archive.getinfo(name).file_size)
            with archive.open(member) as raw:
                yield io.TextIOWrapper(raw, encoding="utf-8", newline=""), member
    else:
        with path.open(newline="", encoding="utf-8") as handle:
            yield handle, path.name


def ingest_ebd(spec: IngestSpec) -> IngestSummary:
    """Filter an EBD extract into a derived point-level table + provenance sidecar."""
    for code in spec.species:
        if code not in TAXONOMY_SNAPSHOT:
            raise ValueError(f"Unknown species code '{code}' (not in taxonomy snapshot)")
    common_to_code = {TAXONOMY_SNAPSHOT[code]["common"].lower(): code for code in spec.species}
    months = set(spec.months)

    out_path = Path(spec.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = Path(spec.ebd_path)
    source_size = source_path.stat().st_size

    rows_scanned = 0
    rows_kept = 0
    per_species = dict.fromkeys(spec.species, 0)

    with (
        _open_text_member(source_path, "ebd_") as (source, source_member),
        out_path.open("w", newline="", encoding="utf-8") as destination,
    ):
        reader = csv.reader(source, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"EBD file is empty: {source_path}") from exc
        index = _resolve_columns(header)
        writer = csv.writer(destination)
        writer.writerow(OUTPUT_COLUMNS)
        width = len(header)

        for row in reader:
            rows_scanned += 1
            if len(row) < width:
                continue
            code = common_to_code.get(row[index["common_name"]].strip().lower())
            if code is None:
                continue
            date = row[index["observation_date"]].strip()
            try:
                year = int(date[0:4])
                month = int(date[5:7])
            except ValueError:
                continue
            if month not in months:
                continue
            if spec.complete_checklists_only:
                flag_index = index.get("all_species_reported")
                if flag_index is not None:
                    flag = row[flag_index].strip().lower()
                    if flag not in TRUE_FLAGS:
                        continue
            count_raw = row[index["observation_count"]].strip()
            try:
                count = 0.0 if count_raw.lower() == "x" or count_raw == "" else float(count_raw)
                latitude = float(row[index["latitude"]])
                longitude = float(row[index["longitude"]])
            except ValueError:
                continue
            writer.writerow(
                (
                    code,
                    row[index["scientific_name"]].strip(),
                    date,
                    year,
                    month,
                    latitude,
                    longitude,
                    count,
                )
            )
            rows_kept += 1
            per_species[code] += 1

    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    summary = IngestSummary(
        source=source_path.name,
        source_size_bytes=source_size,
        output=out_path.name,
        output_sha256=digest,
        filters={
            "species": list(spec.species),
            "months": list(spec.months),
            "complete_checklists_only": spec.complete_checklists_only,
        },
        rows_scanned=rows_scanned,
        rows_kept=rows_kept,
        per_species=dict(sorted(per_species.items())),
        source_member=source_member,
    )
    sidecar = out_path.with_name(out_path.name + ".provenance.json")
    sidecar.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


# ---------------------------------------------------------------------------
# SED join + zero-fill (E-P4.8)
# ---------------------------------------------------------------------------

SED_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "checklist_id": ("sampling event identifier", "samplingeventidentifier"),
    "observation_date": ("observation date", "date"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng"),
    "protocol_type": ("protocol type",),
    "duration_minutes": ("duration minutes",),
    "effort_distance_km": ("effort distance km",),
    "effort_area_ha": ("effort area ha",),
    "number_observers": ("number observers",),
    "all_species_reported": ("all species reported",),
}

SED_REQUIRED_COLUMNS = ("checklist_id", "observation_date", "latitude", "longitude")

ZERO_FILL_COLUMNS = (
    "species_code",
    "checklist_id",
    "observation_date",
    "year",
    "month",
    "latitude",
    "longitude",
    "observation_count",
    "detection",
    "complete_checklist",
    "protocol_type",
    "duration_minutes",
    "effort_distance_km",
    "number_observers",
)

STRUCTURED_PROTOCOLS = ("Stationary", "Traveling")


def _to_float(value: Any) -> float | None:
    text = ("" if value is None else str(value)).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_number(value: float | None) -> str:
    """CSV-friendly number: ints without a trailing ``.0``; empty for None."""
    if value is None:
        return ""
    number = float(value)
    return str(int(number)) if number.is_integer() else repr(number)


@dataclass(frozen=True)
class ZeroFillSpec:
    """Ingestion request for a zero-filled checklist x species table."""

    ebd_path: Path
    sed_path: Path
    out_csv: Path
    species: tuple[str, ...]
    months: tuple[int, ...] = (5, 6, 7, 8)
    complete_checklists_only: bool = True
    protocols: tuple[str, ...] | None = STRUCTURED_PROTOCOLS


@dataclass(frozen=True)
class ZeroFillSummary:
    """Provenance summary for a zero-filled derived table."""

    source_ebd: str
    source_sed: str
    source_ebd_size_bytes: int
    source_sed_size_bytes: int
    output: str
    output_sha256: str
    rows: int
    checklists: int
    per_species_detections: dict[str, int]
    per_species_non_detections: dict[str, int]
    unspecified_counts: int
    filters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_sed_events(
    path: Path | str,
    *,
    months: tuple[int, ...] = (5, 6, 7, 8),
    complete_checklists_only: bool = True,
    protocols: tuple[str, ...] | None = STRUCTURED_PROTOCOLS,
) -> dict[str, dict[str, Any]]:
    """Read filtered SED events, keyed by sampling-event identifier.

    Observer identifiers are never carried into the returned records.
    """
    events: dict[str, dict[str, Any]] = {}
    with _open_text_member(Path(path), "sampling") as (handle, _member):
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"SED file is empty: {path}") from exc
        index = _resolve_columns(header, SED_COLUMN_ALIASES, SED_REQUIRED_COLUMNS)
        width = len(header)
        for row in reader:
            if len(row) < width:
                continue
            date = row[index["observation_date"]].strip()
            try:
                year = int(date[0:4])
                month = int(date[5:7])
            except ValueError:
                continue
            if month not in months:
                continue
            complete = True
            flag_index = index.get("all_species_reported")
            if flag_index is not None:
                complete = row[flag_index].strip().lower() in TRUE_FLAGS
            if complete_checklists_only and not complete:
                continue
            if protocols is not None:
                protocol_index = index.get("protocol_type")
                if protocol_index is None or row[protocol_index].strip() not in protocols:
                    continue
            checklist_id = row[index["checklist_id"]].strip()
            if not checklist_id:
                continue
            events[checklist_id] = {
                "observation_date": date,
                "year": year,
                "month": month,
                "latitude": _to_float(row[index["latitude"]]),
                "longitude": _to_float(row[index["longitude"]]),
                "complete_checklist": complete,
                "protocol_type": (
                    row[index["protocol_type"]].strip() if "protocol_type" in index else ""
                ),
                "duration_minutes": (
                    _to_float(row[index["duration_minutes"]])
                    if "duration_minutes" in index
                    else None
                ),
                "effort_distance_km": (
                    _to_float(row[index["effort_distance_km"]])
                    if "effort_distance_km" in index
                    else None
                ),
                "number_observers": (
                    _to_float(row[index["number_observers"]])
                    if "number_observers" in index
                    else None
                ),
            }
    return events


def ingest_ebd_zero_filled(spec: ZeroFillSpec) -> ZeroFillSummary:
    """Join EBD detections to filtered SED events and zero-fill the species grid.

    ``X`` counts are recorded as detections with an **empty** ``observation_count``
    (not zero), so downstream fitting can treat them as censored rather than as
    absences. Observer identifiers are never written.
    """
    for code in spec.species:
        if code not in TAXONOMY_SNAPSHOT:
            raise ValueError(f"Unknown species code '{code}' (not in taxonomy snapshot)")
    common_to_code = {TAXONOMY_SNAPSHOT[code]["common"].lower(): code for code in spec.species}

    events = read_sed_events(
        spec.sed_path,
        months=spec.months,
        complete_checklists_only=spec.complete_checklists_only,
        protocols=spec.protocols,
    )

    detections: dict[tuple[str, str], float | None] = {}
    unspecified_counts = 0
    ebd_path = Path(spec.ebd_path)
    with _open_text_member(ebd_path, "ebd_") as (handle, _member):
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"EBD file is empty: {ebd_path}") from exc
        index = _resolve_columns(header)
        checklist_index = index.get("checklist_id")
        if checklist_index is None:
            raise ValueError(
                f"EBD file is missing 'SAMPLING EVENT IDENTIFIER'; cannot join to SED: {ebd_path}"
            )
        width = len(header)
        for row in reader:
            if len(row) < width:
                continue
            checklist_id = row[checklist_index].strip()
            if checklist_id not in events:
                continue
            code = common_to_code.get(row[index["common_name"]].strip().lower())
            if code is None:
                continue
            count_raw = row[index["observation_count"]].strip()
            if count_raw.lower() == "x":
                detections[(checklist_id, code)] = None
                unspecified_counts += 1
            else:
                detections[(checklist_id, code)] = _to_float(count_raw)

    out_path = Path(spec.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    per_detections = dict.fromkeys(spec.species, 0)
    per_non_detections = dict.fromkeys(spec.species, 0)
    rows = 0
    with out_path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.writer(destination)
        writer.writerow(ZERO_FILL_COLUMNS)
        for checklist_id in sorted(events):
            event = events[checklist_id]
            for code in sorted(spec.species):
                key = (checklist_id, code)
                detected = key in detections
                count = detections.get(key) if detected else 0.0
                if detected:
                    per_detections[code] += 1
                else:
                    per_non_detections[code] += 1
                writer.writerow(
                    (
                        code,
                        checklist_id,
                        event["observation_date"],
                        event["year"],
                        event["month"],
                        event["latitude"],
                        event["longitude"],
                        _format_number(count),
                        int(detected),
                        int(bool(event["complete_checklist"])),
                        event["protocol_type"],
                        _format_number(event["duration_minutes"]),
                        _format_number(event["effort_distance_km"]),
                        _format_number(event["number_observers"]),
                    )
                )
                rows += 1

    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    summary = ZeroFillSummary(
        source_ebd=ebd_path.name,
        source_sed=Path(spec.sed_path).name,
        source_ebd_size_bytes=ebd_path.stat().st_size,
        source_sed_size_bytes=Path(spec.sed_path).stat().st_size,
        output=out_path.name,
        output_sha256=digest,
        rows=rows,
        checklists=len(events),
        per_species_detections=dict(sorted(per_detections.items())),
        per_species_non_detections=dict(sorted(per_non_detections.items())),
        unspecified_counts=unspecified_counts,
        filters={
            "species": list(spec.species),
            "months": list(spec.months),
            "complete_checklists_only": spec.complete_checklists_only,
            "protocols": list(spec.protocols) if spec.protocols is not None else None,
        },
    )
    sidecar = out_path.with_name(out_path.name + ".provenance.json")
    sidecar.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
