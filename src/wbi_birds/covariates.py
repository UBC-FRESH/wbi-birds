"""Raster covariate preparation for the bird regression (E-P4.6).

Ports the ``prepData`` half of the R/SpaDES ``fitBirdBiomassModel`` module:

- sample kNN species-biomass, merchantable-volume, stand-age, and land-cover
  rasters at observation points;
- scale species biomass by merchantable volume and aggregate to
  softwood/hardwood;
- prefer FRI stand age where available, else project the kNN age to the
  observation year and drop negative projections.

The heavy raster dependency (``rasterio``) is optional — install
``wbi-birds[covariates]``. The transforms themselves live in
:mod:`wbi_birds.regression` and are tested without it; the row assembly here
takes already-sampled arrays so it is testable too.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from wbi_birds.regression import (
    STAND_AGE_BASE_YEAR,
    aggregate_wood_types,
    correct_stand_age,
)


class CovariateError(ValueError):
    """Raised when raster covariates cannot be prepared."""


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def sample_rasters(
    layers: Mapping[str, Path | str],
    points: Sequence[tuple[float, float]],
    *,
    band: int = 1,
    nodata: Sequence[float] | None = None,
) -> dict[str, list[float | None]]:
    """Sample one band from each raster at ``(x, y)`` points.

    Requires the optional ``rasterio`` dependency. Raster-declared nodata values
    are returned as ``None`` (dropped downstream). CRS handling is the caller's
    responsibility: points and rasters must share a CRS.
    """
    try:
        import rasterio
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise CovariateError(
            "raster sampling requires the optional 'rasterio' dependency; "
            "install with `pip install wbi-birds[covariates]`."
        ) from exc

    result: dict[str, list[float | None]] = {}
    for name, path in layers.items():
        with rasterio.open(path) as src:
            declared = src.nodata
            values: list[float | None] = []
            for sample in src.sample(points, indexes=band):
                value = float(sample[0])
                if declared is not None and value == declared:
                    values.append(None)
                else:
                    values.append(value)
        result[name] = values
    return result


def build_covariate_rows(
    samples: Mapping[str, Sequence[float | None]],
    *,
    softwood_species: Sequence[str],
    hardwood_species: Sequence[str],
    merchantable_volume: str,
    knn_age: str,
    observation_year: Sequence[int] | int,
    fri_age: str | None = None,
    base_year: int = STAND_AGE_BASE_YEAR,
    factor: float = 0.01,
) -> list[dict[str, float]]:
    """Assemble regression rows from sampled covariates.

    Returns one dict per retained observation with keys ``softwood``,
    ``hardwood`` and ``age``. Rows whose age cannot be resolved (missing kNN age
    or a negative projection to the observation year) are dropped, matching the
    R module. FRI age takes precedence where present.
    """
    n = len(next(iter(samples.values()))) if samples else 0
    years = observation_year if isinstance(observation_year, Sequence) else [observation_year] * n
    if len(years) != n:
        raise CovariateError(
            f"observation_year has {len(years)} value(s) but samples have {n} row(s)"
        )
    if fri_age is not None and fri_age not in samples:
        raise CovariateError(f"fri_age layer '{fri_age}' was not sampled")

    rows: list[dict[str, float]] = []
    for index in range(n):
        species = {
            name: samples[name][index]
            for name in (*softwood_species, *hardwood_species)
            if name in samples and not _is_missing(samples[name][index])
        }
        volume = samples[merchantable_volume][index]
        softwood, hardwood = aggregate_wood_types(
            species,
            softwood_species=softwood_species,
            hardwood_species=hardwood_species,
            merchantable_volume=volume,
            factor=factor,
        )
        age: float | None = None
        if fri_age is not None and not _is_missing(samples[fri_age][index]):
            age = float(samples[fri_age][index])
        else:
            age = correct_stand_age(samples[knn_age][index], int(years[index]), base_year=base_year)
        if age is None:
            continue
        rows.append({"softwood": softwood, "hardwood": hardwood, "age": age})
    return rows
