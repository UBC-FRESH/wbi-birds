"""Native Python port of the bird-regression logic (E-P4.6).

This replaces the R/SpaDES ``fitBirdBiomassModel`` lineage with a single-language
implementation inside the engine. It covers the full original pipeline:

- kNN stand-age projection to the observation year (dropping negatives);
- species biomass scaling by merchantable volume and aggregation into
  softwood/hardwood;
- Poisson GLM with the full ``summary()`` statistics (coefficients, std. errors,
  z, p, null/residual deviance, AIC, dispersion);
- a stepwise-AIC selection equivalent to ``MASS::stepAIC``.

The raster-sampling half of the original module lives in
:mod:`wbi_birds.covariates` (optional ``rasterio`` dependency). Nothing here
imports R, SpaDES, or shells out.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

STAND_AGE_BASE_YEAR = 2011
DEFAULT_FEATURES = ("softwood", "hardwood", "age")
INTERCEPT = "intercept"


class RegressionError(ValueError):
    """Raised when regression inputs are invalid or the fit cannot proceed."""


# ---------------------------------------------------------------------------
# Covariate transforms (ports of the R prepData logic)
# ---------------------------------------------------------------------------


def correct_stand_age(
    age: float | None,
    observation_year: int,
    *,
    base_year: int = STAND_AGE_BASE_YEAR,
    min_age: float = 0.0,
) -> float | None:
    """Project a kNN stand age (``base_year`` snapshot) to the observation year.

    Mirrors ``age := age - (2011 - YEAR)`` followed by dropping negative values
    in the R module. Returns ``None`` when the age is missing or projects below
    ``min_age`` (such rows are dropped).
    """
    if age is None or (isinstance(age, float) and math.isnan(age)):
        return None
    corrected = float(age) - (int(base_year) - int(observation_year))
    if corrected < min_age:
        return None
    return corrected


def scale_species_biomass(
    biomass: float | None,
    merchantable_volume: float | None,
    *,
    factor: float = 0.01,
) -> float:
    """Species biomass scaled by merchantable volume (``0.01 * biomass * mvol``)."""
    if biomass is None or merchantable_volume is None:
        return 0.0
    if isinstance(biomass, float) and math.isnan(biomass):
        return 0.0
    if isinstance(merchantable_volume, float) and math.isnan(merchantable_volume):
        return 0.0
    return float(factor) * float(biomass) * float(merchantable_volume)


def aggregate_wood_types(
    species_biomass: Mapping[str, float | None],
    *,
    softwood_species: Iterable[str],
    hardwood_species: Iterable[str],
    merchantable_volume: float | None = None,
    factor: float = 0.01,
) -> tuple[float, float]:
    """Aggregate scaled species biomass into ``(softwood, hardwood)``.

    ``merchantable_volume=None`` skips the scaling (useful when the table already
    carries volume-scaled biomass).
    """
    scale = 1.0 if merchantable_volume is None else factor * float(merchantable_volume)

    def total(species: Iterable[str]) -> float:
        return float(
            sum(
                float(species_biomass.get(name) or 0.0)
                for name in species
                if species_biomass.get(name) is not None
            )
        )

    return scale * total(softwood_species), scale * total(hardwood_species)


# ---------------------------------------------------------------------------
# Design matrix and Poisson fit with full statistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PoissonFitResult:
    """Full Poisson GLM fit statistics (R ``summary()`` equivalent)."""

    coefficients: Mapping[str, float]
    std_errors: Mapping[str, float]
    z_values: Mapping[str, float]
    p_values: Mapping[str, float]
    n: int
    null_deviance: float
    residual_deviance: float
    log_likelihood: float
    aic: float
    converged: bool
    covariance: tuple[tuple[float, ...], ...] = field(default=(), repr=False)

    @property
    def feature_names(self) -> tuple[str, ...]:
        return tuple(self.coefficients)

    @property
    def dispersion(self) -> float:
        """Residual deviance / residual degrees of freedom (Poisson = 1 ideal)."""
        dof = self.n - len(self.coefficients)
        return self.residual_deviance / dof if dof > 0 else float("nan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "coefficients": dict(self.coefficients),
            "std_errors": dict(self.std_errors),
            "z_values": dict(self.z_values),
            "p_values": dict(self.p_values),
            "n": self.n,
            "null_deviance": self.null_deviance,
            "residual_deviance": self.residual_deviance,
            "log_likelihood": self.log_likelihood,
            "aic": self.aic,
            "dispersion": self.dispersion,
            "converged": self.converged,
        }


def design_matrix(
    features: np.ndarray, feature_names: Sequence[str]
) -> tuple[np.ndarray, tuple[str, ...]]:
    """Prepend an intercept column to a 2-D feature array."""
    matrix = np.asarray(features, dtype=float)
    if matrix.ndim != 2:
        raise RegressionError("features must be a 2-D array (n_observations, n_features)")
    if matrix.shape[1] != len(feature_names):
        raise RegressionError(
            f"features has {matrix.shape[1]} column(s) but {len(feature_names)} name(s)"
        )
    intercept = np.ones((matrix.shape[0], 1), dtype=float)
    return np.hstack([intercept, matrix]), (INTERCEPT, *feature_names)


def _validate(features: np.ndarray, response: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(features, dtype=float)
    y = np.asarray(response, dtype=float)
    if x.ndim != 2 or y.ndim != 1 or x.shape[0] != y.shape[0]:
        raise RegressionError("features (n, p) and response (n,) must share n")
    if x.shape[0] == 0:
        raise RegressionError("cannot fit on zero observations")
    if np.any(y < 0):
        raise RegressionError("Poisson response must be non-negative")
    return x, y


def _poisson_deviance(y: np.ndarray, mu: np.ndarray) -> float:
    mu = np.clip(mu, 1e-12, None)
    ratio = np.where(y > 0, y * np.log(np.where(y > 0, y, 1.0) / mu), 0.0)
    return float(2.0 * np.sum(ratio - (y - mu)))


def _log_likelihood(y: np.ndarray, mu: np.ndarray) -> float:
    mu = np.clip(mu, 1e-12, None)
    return float(np.sum(y * np.log(mu) - mu - gammaln(y + 1.0)))


def fit_poisson_glm(
    features: np.ndarray,
    response: np.ndarray,
    feature_names: Sequence[str] = DEFAULT_FEATURES,
) -> PoissonFitResult:
    """Fit ``count ~ intercept + features`` by Poisson MLE with full statistics.

    Coefficients are on the log scale (R ``family = "poisson"`` uses the log
    link); standard errors come from the analytic Fisher information
    ``(X' W X)^-1`` with ``W = diag(mu)``.
    """
    x_raw, y = _validate(features, response)
    x, names = design_matrix(x_raw, feature_names)
    n, k = x.shape

    def negative_loglik(beta: np.ndarray) -> float:
        eta = np.clip(x @ beta, -30.0, 30.0)
        return float(np.sum(np.exp(eta) - y * eta))

    def gradient(beta: np.ndarray) -> np.ndarray:
        eta = np.clip(x @ beta, -30.0, 30.0)
        return x.T @ (np.exp(eta) - y)

    result = minimize(
        negative_loglik,
        np.zeros(k),
        jac=gradient,
        method="L-BFGS-B",
        options={"maxiter": 5000, "ftol": 1e-14, "gtol": 1e-10},
    )
    beta = np.asarray(result.x, dtype=float)
    eta = np.clip(x @ beta, -30.0, 30.0)
    mu = np.exp(eta)

    # Analytic covariance and derived statistics.
    weights = np.clip(mu, 1e-12, None)
    xtwx = x.T @ (x * weights[:, None])
    covariance = np.linalg.pinv(xtwx)
    variance = np.clip(np.diag(covariance), 0.0, None)
    se = np.sqrt(variance)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(se > 0, beta / se, np.nan)
    p = np.array(
        [math.erfc(abs(value) / math.sqrt(2.0)) if np.isfinite(value) else np.nan for value in z]
    )

    null_mu = np.full(n, float(np.mean(y)))
    return PoissonFitResult(
        coefficients={name: float(value) for name, value in zip(names, beta, strict=True)},
        std_errors={name: float(value) for name, value in zip(names, se, strict=True)},
        z_values={name: float(value) for name, value in zip(names, z, strict=True)},
        p_values={name: float(value) for name, value in zip(names, p, strict=True)},
        n=n,
        null_deviance=_poisson_deviance(y, null_mu),
        residual_deviance=_poisson_deviance(y, mu),
        log_likelihood=_log_likelihood(y, mu),
        aic=float(2 * k - 2 * _log_likelihood(y, mu)),
        converged=bool(result.success) or float(np.linalg.norm(gradient(beta))) < 1e-3,
        covariance=tuple(tuple(float(v) for v in row) for row in covariance),
    )


def _fit_subset(
    features: np.ndarray,
    response: np.ndarray,
    names: Sequence[str],
    subset: Sequence[str],
) -> PoissonFitResult:
    if not subset:
        x = np.zeros((len(response), 0), dtype=float)
        return fit_poisson_glm(x, response, ())
    index = [list(names).index(name) for name in subset]
    return fit_poisson_glm(np.asarray(features)[:, index], response, subset)


def stepwise_aic(
    features: np.ndarray,
    response: np.ndarray,
    feature_names: Sequence[str] = DEFAULT_FEATURES,
    *,
    direction: str = "both",
    max_steps: int = 100,
) -> tuple[tuple[str, ...], PoissonFitResult]:
    """Stepwise AIC selection (port of ``MASS::stepAIC``).

    ``direction`` is one of ``"backward"``, ``"forward"`` or ``"both"``.
    Returns the selected feature names (without the intercept) and the fit.
    """
    if direction not in {"backward", "forward", "both"}:
        raise RegressionError(f"unknown stepwise direction '{direction}'")
    all_names = list(feature_names)
    current: list[str] = [] if direction == "forward" else list(all_names)
    best = _fit_subset(features, response, all_names, current)

    for _ in range(max_steps):
        candidates: list[tuple[str, ...]] = []
        if direction in {"backward", "both"}:
            candidates.extend(tuple(name for name in current if name != drop) for drop in current)
        if direction in {"forward", "both"}:
            candidates.extend((*current, name) for name in all_names if name not in current)
        improved = False
        for candidate in candidates:
            if not candidate or tuple(candidate) == tuple(current):
                continue
            fit = _fit_subset(features, response, all_names, candidate)
            if fit.aic < best.aic - 1e-8:
                current, best, improved = list(candidate), fit, True
                break
        if not improved:
            break
    return tuple(current), best


def linear_predictor(coefficients: Mapping[str, float], features: Mapping[str, float]) -> float:
    """Evaluate the fitted log-mean ``eta = intercept + sum(beta * x)``."""
    eta = float(coefficients.get(INTERCEPT, coefficients.get("intercept", 0.0)))
    for name, value in features.items():
        eta += float(coefficients.get(name, 0.0)) * float(value)
    return eta


def expected_count(coefficients: Mapping[str, float], features: Mapping[str, float]) -> float:
    """Expected count ``exp(eta)`` for a fitted Poisson (log-link) model."""
    return float(math.exp(np.clip(linear_predictor(coefficients, features), -30.0, 30.0)))


def quasi_poisson_summary(result: PoissonFitResult) -> dict[str, dict[str, float]]:
    """Standard errors and tests rescaled by the dispersion (quasi-Poisson).

    The Poisson covariance is multiplied by the dispersion, so each standard error is
    scaled by its square root. Coefficients are unchanged; z and p values follow from the
    scaled standard errors.
    """
    dispersion = result.dispersion
    if not math.isfinite(dispersion) or dispersion <= 0.0:
        raise ValueError(f"dispersion must be positive and finite, got {dispersion!r}")
    scale = math.sqrt(dispersion)
    names = tuple(result.coefficients)
    std_errors = {name: float(result.std_errors[name]) * scale for name in names}
    z_values = {
        name: (
            float(result.coefficients[name]) / std_errors[name]
            if std_errors[name] > 0.0
            else math.nan
        )
        for name in names
    }
    p_values = {
        name: math.erfc(abs(z) / math.sqrt(2.0)) if math.isfinite(z) else math.nan
        for name, z in z_values.items()
    }
    return {"std_errors": std_errors, "z_values": z_values, "p_values": p_values}
