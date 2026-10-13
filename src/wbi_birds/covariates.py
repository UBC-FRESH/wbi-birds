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


WOOD_TYPE_DEFINITIONS: tuple[str, ...] = ("volume_allocated", "legacy_biomass_scaled")
DEFAULT_WOOD_TYPE_DEFINITION = "volume_allocated"


def _is_scalar(value: Any) -> bool:
    """True for a single year-like value (int, numpy scalar), False for any sequence/array."""
    return not hasattr(value, "__len__")


def _clean(value: Any) -> float | None:
    """Float value, or ``None`` for missing/NaN input (numpy scalars included)."""
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else number


def allocate_wood_volume(
    merchantable_volume: float | None,
    softwood_biomass: float,
    hardwood_biomass: float,
) -> tuple[float, float] | None:
    """Allocate merchantable volume to softwood/hardwood by classified biomass share.

    The accepted unit contract (``planning/unit-contract-decision.md``)::

        swvol = mvol * sw / (sw + hw)        hwvol = mvol * hw / (sw + hw)

    with ``sw`` and ``hw`` the biomass summed over the classified softwood and
    hardwood species. Hence ``swvol + hwvol == mvol`` exactly, so the fit
    covariates share a unit and a total with the planning yield curves
    (``swdvol + hwdvol``). Returns ``None`` when the share is undefined.
    """
    volume = _clean(merchantable_volume)
    if volume is None:
        return None
    if volume == 0.0:
        # No merchantable volume: the wood-type volumes are zero whatever the shares
        # (e.g. recently harvested or non-forest states). Not a 0/0 case.
        return 0.0, 0.0
    sw = float(softwood_biomass)
    hw = float(hardwood_biomass)
    total = sw + hw
    if not math.isfinite(total) or total <= 0.0:
        # Positive volume with no classified biomass: the share is undefined.
        return None
    return volume * sw / total, volume * hw / total


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
    definition: str = DEFAULT_WOOD_TYPE_DEFINITION,
    response: Sequence[float] | None = None,
) -> list[dict[str, float]]:
    """Assemble regression rows from sampled covariates.

    ``definition`` selects the wood-type state vector:

    - ``volume_allocated`` (default, the accepted v2 contract): ``softwood`` and
      ``hardwood`` are merchantable volume allocated by classified biomass share,
      so ``softwood + hardwood == mvol``;
    - ``legacy_biomass_scaled``: ``factor * biomass * mvol`` summed by wood type
      (the 2019 R definition; parity reference only).

    Missing values follow the R module's NA propagation: a row with any missing
    classified species, merchantable volume, or resolvable age is dropped. A
    classified species that was not sampled at all is a configuration error.
    FRI age takes precedence where present. When ``response`` is given, each row
    carries its aligned ``observation_count``.
    """
    if definition not in WOOD_TYPE_DEFINITIONS:
        raise CovariateError(
            f"unknown wood-type definition '{definition}' (expected one of {WOOD_TYPE_DEFINITIONS})"
        )
    n = len(next(iter(samples.values()))) if samples else 0
    # numpy arrays are not collections.abc.Sequence; treat any non-scalar as a sequence.
    years = [observation_year] * n if _is_scalar(observation_year) else observation_year
    if len(years) != n:
        raise CovariateError(
            f"observation_year has {len(years)} value(s) but samples have {n} row(s)"
        )
    if response is not None and len(response) != n:
        raise CovariateError(f"response has {len(response)} value(s) but samples have {n} row(s)")
    if fri_age is not None and fri_age not in samples:
        raise CovariateError(f"fri_age layer '{fri_age}' was not sampled")
    classified = (*softwood_species, *hardwood_species)
    unsampled = [
        name for name in (*classified, merchantable_volume, knn_age) if name not in samples
    ]
    if unsampled:
        raise CovariateError(f"layer(s) not sampled: {', '.join(sorted(set(unsampled)))}")

    rows: list[dict[str, float]] = []
    for index in range(n):
        species = {name: _clean(samples[name][index]) for name in classified}
        volume = _clean(samples[merchantable_volume][index])
        if volume is None or any(value is None for value in species.values()):
            continue
        if definition == "volume_allocated":
            sw_biomass = sum(float(species[name]) for name in softwood_species)
            hw_biomass = sum(float(species[name]) for name in hardwood_species)
            allocated = allocate_wood_volume(volume, sw_biomass, hw_biomass)
            if allocated is None:
                continue
            softwood, hardwood = allocated
        else:
            softwood, hardwood = aggregate_wood_types(
                {name: float(value) for name, value in species.items() if value is not None},
                softwood_species=softwood_species,
                hardwood_species=hardwood_species,
                merchantable_volume=volume,
                factor=factor,
            )
        if fri_age is not None and _clean(samples[fri_age][index]) is not None:
            age: float | None = float(_clean(samples[fri_age][index]))  # type: ignore[arg-type]
        else:
            age = correct_stand_age(
                _clean(samples[knn_age][index]), int(years[index]), base_year=base_year
            )
        if age is None:
            continue
        row: dict[str, float] = {
            "softwood": softwood,
            "hardwood": hardwood,
            "age": age,
            "source_index": index,
        }
        if response is not None:
            row["observation_count"] = float(response[index])
        rows.append(row)
    return rows
