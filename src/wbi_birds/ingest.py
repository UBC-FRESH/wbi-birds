"""EBD-derived ingestion (E-P4.3).

Streams the private eBird Basic Dataset extract (tab-delimited, as received)
into a derived point-level table filtered to the species suite and breeding
months, with a provenance sidecar. **Raw content never leaves the private
store** — the engine emits derived products only, and observer identifiers are
never carried into the output.

Legacy-compatible convention: observation count ``X`` maps to ``0.0``.

Accepts either an EBD ``.txt`` file or a ``.zip`` archive containing one
(selects the largest ``ebd_*.txt`` member).
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


def _resolve_columns(header: list[str]) -> dict[str, int]:
    normalized = [_normalize(name) for name in header]
    index: dict[str, int] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                index[field] = normalized.index(alias)
                break
    missing = [field for field in REQUIRED_COLUMNS if field not in index]
    if missing:
        raise ValueError(
            f"EBD file is missing required column(s): {', '.join(missing)} (header: {header!r})"
        )
    return index


@contextmanager
def _open_ebd_text(path: Path) -> Iterator[tuple[Any, str]]:
    """Yield (text stream, member name) for an EBD ``.txt`` or ``.zip`` archive."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".txt") and "ebd_" in Path(name).name.lower()
            ]
            if not members:
                raise ValueError(f"No EBD .txt member found in archive: {path}")
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
        _open_ebd_text(source_path) as (source, source_member),
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
