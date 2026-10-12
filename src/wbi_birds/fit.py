"""Anticipation-function fitting support (E-P4.4).

Two paths:

- ``provided``: stage R-fitted coefficients (the `fitBirdBiomassModel` lineage —
  the manuscript's primary path) into an instance, validated against the
  taxonomy snapshot.
- ``poisson``: engine-native Poisson MLE fit of ``count ~ swvol + hwvol + age``
  (scipy) from a covariates table — for verification/regeneration once the
  eBird extract and KNN covariates land.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from scipy.optimize import minimize

from wbi_birds.bird import AnticipationCoefficients
from wbi_birds.responses import ResponseTable, merge_response_table, read_response_tables
from wbi_birds.taxonomy import TAXONOMY_SNAPSHOT

FEATURES = ("swvol", "hwvol", "age")
COEFFICIENT_KEYS = ("intercept", "swvol", "hwvol", "age")


class FitError(ValueError):
    """Raised when coefficients cannot be staged or fitted."""


@dataclass(frozen=True)
class FitResult:
    """Outcome of an engine-native Poisson fit."""

    coefficients: AnticipationCoefficients
    n_observations: int
    converged: bool
    negative_loglik: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_covariates(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise FitError(f"Covariates table is empty: {path}")
        required = {"observation_count", *FEATURES}
        missing = required - set(reader.fieldnames)
        if missing:
            raise FitError(f"Covariates table missing column(s): {sorted(missing)}")
        design: list[list[float]] = []
        response: list[float] = []
        for row in reader:
            design.append([1.0, float(row["swvol"]), float(row["hwvol"]), float(row["age"])])
            response.append(float(row["observation_count"]))
    if not design:
        raise FitError(f"Covariates table has no data rows: {path}")
    return np.asarray(design), np.asarray(response)


def fit_poisson_glm(covariates_csv: Path | str) -> FitResult:
    """Poisson MLE fit of ``count ~ intercept + swvol + hwvol + age``."""
    design, response = _read_covariates(Path(covariates_csv))
    features = design[:, 1:]
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale == 0.0] = 1.0
    standardized = np.column_stack([np.ones(design.shape[0]), (features - mean) / scale])

    def negative_loglik(beta: np.ndarray) -> float:
        eta = np.clip(standardized @ beta, -30.0, 30.0)
        return float(np.sum(np.exp(eta) - response * eta))

    result = minimize(
        negative_loglik,
        np.zeros(standardized.shape[1]),
        method="L-BFGS-B",
        options={"maxiter": 2000, "ftol": 1e-12, "gtol": 1e-9},
    )
    beta = result.x
    gradient = getattr(result, "jac", None)
    gradient_norm = (
        float(np.linalg.norm(gradient)) / max(1, design.shape[0])
        if gradient is not None
        else float("inf")
    )
    slopes = beta[1:] / scale
    intercept = float(beta[0] - np.sum(beta[1:] * mean / scale))
    return FitResult(
        coefficients=AnticipationCoefficients(
            intercept=intercept,
            swvol=float(slopes[0]),
            hwvol=float(slopes[1]),
            age=float(slopes[2]),
        ),
        n_observations=int(design.shape[0]),
        converged=bool(result.success) or gradient_norm < 1e-3,
        negative_loglik=float(result.fun),
    )


def _validate_species_map(
    species_map: Mapping[str, Any], origin: str, *, allow_empty: bool = False
) -> dict[str, dict[str, float]]:
    normalized: dict[str, dict[str, float]] = {}
    for code, entry in species_map.items():
        if code not in TAXONOMY_SNAPSHOT:
            raise FitError(f"Unknown species code '{code}' in {origin}")
        if not isinstance(entry, Mapping):
            raise FitError(f"Species entry for '{code}' is not a mapping in {origin}")
        coefficients = AnticipationCoefficients.from_mapping(entry)  # type: ignore[arg-type]
        normalized[code] = {
            "intercept": coefficients.intercept,
            "swvol": coefficients.swvol,
            "hwvol": coefficients.hwvol,
            "age": coefficients.age,
        }
    if not normalized and not allow_empty:
        raise FitError(f"No species entries found in {origin}")
    return normalized


def _write_coefficients(
    instance_root: Path,
    species_map: Mapping[str, Mapping[str, float]],
    *,
    source: Mapping[str, Any],
) -> Path:
    path = instance_root / "bird" / "coefficients.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": dict(source),
        "species": {code: dict(species_map[code]) for code in sorted(species_map)},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def stage_coefficients(source_yaml: Path | str, instance_root: Path | str) -> Path:
    """Stage an externally fitted coefficients file into the instance (validated)."""
    source_path = Path(source_yaml)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FitError(f"Coefficients file is not a mapping: {source_path}")
    species_map = _validate_species_map(data.get("species") or {}, str(source_path))
    source = data.get("source")
    if not isinstance(source, Mapping):
        source = {"fit": "provided"}
    else:
        source = dict(source)
        source["fit"] = "provided"
    return _write_coefficients(Path(instance_root), species_map, source=source)


def update_instance_coefficients(
    instance_root: Path | str,
    species_code: str,
    coefficients: AnticipationCoefficients,
    *,
    fit_note: str,
) -> Path:
    """Merge one species' fitted coefficients into the instance (others preserved)."""
    if species_code not in TAXONOMY_SNAPSHOT:
        raise FitError(f"Unknown species code '{species_code}'")
    root = Path(instance_root)
    path = root / "bird" / "coefficients.yaml"
    existing: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded
    species_map = _validate_species_map(existing.get("species") or {}, str(path), allow_empty=True)
    species_map[species_code] = {
        "intercept": coefficients.intercept,
        "swvol": coefficients.swvol,
        "hwvol": coefficients.hwvol,
        "age": coefficients.age,
    }
    source = existing.get("source")
    if not isinstance(source, Mapping):
        source = {}
    source = dict(source)
    source["fit"] = fit_note
    return _write_coefficients(root, species_map, source=source)


def stage_response_table(
    instance_root: Path | str,
    table: ResponseTable,
    *,
    fit_note: str = "provided",
) -> Path:
    """Stage one species' precomputed response table into an instance.

    Response tables carry the exact per-(development type, age) values of any
    fitted model (linear or not); see :mod:`wbi_birds.responses`.
    """
    if table.species_code not in TAXONOMY_SNAPSHOT:
        raise FitError(f"Unknown species code '{table.species_code}'")
    if not table.values:
        raise FitError(f"Response table for '{table.species_code}' has no values")
    source = dict(table.source)
    source["fit"] = fit_note
    staged = ResponseTable(
        species_code=table.species_code,
        values=table.values,
        sd=table.sd,
        source=source,
    )
    return merge_response_table(Path(instance_root), staged)


def stage_response_table_from_csv(
    source_csv: Path | str,
    instance_root: Path | str,
    species_code: str,
    *,
    fit_note: str = "provided",
) -> Path:
    """Stage one species from an externally produced ``response_table.csv``."""
    tables = read_response_tables(Path(source_csv))
    if species_code not in tables:
        raise FitError(
            f"No response table for species '{species_code}' in {source_csv} "
            f"(available: {', '.join(sorted(tables))})."
        )
    return stage_response_table(instance_root, tables[species_code], fit_note=fit_note)


def fit_and_stage(
    covariates_csv: Path | str,
    instance_root: Path | str,
    species_code: str,
) -> tuple[FitResult, Path]:
    """Fit via Poisson MLE and merge the result into the instance."""
    result = fit_poisson_glm(covariates_csv)
    path = update_instance_coefficients(
        instance_root, species_code, result.coefficients, fit_note="poisson_mle"
    )
    return result, path


def make_covariates_csv(
    design: Sequence[tuple[float, float, float]],
    counts: Sequence[float],
    out_csv: Path | str,
) -> Path:
    """Write a covariates table (test/verification helper)."""
    path = Path(out_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("observation_count", *FEATURES))
        for (swvol, hwvol, age), count in zip(design, counts, strict=True):
            writer.writerow((count, swvol, hwvol, age))
    return path
