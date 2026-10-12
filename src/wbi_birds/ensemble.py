"""Ensemble response fitting and coefficient-draw uncertainty (E-P4.9).

Implements the v2 per-species ensemble (``planning/bird-model-v2-spec.md`` §4, §7)
with the core dependencies only (numpy/scipy):

- **members** over the shared state vector ``(softwood, hardwood, age)``:

  - ``poisson``      log-link Poisson GLM (:mod:`wbi_birds.regression`);
  - ``negbin``       log-link negative-binomial (NB2) GLM, dispersion by MLE;
  - ``poly_poisson`` Poisson GLM on standardized quadratic + interaction terms;
  - ``loggauss``     contrast member: OLS on ``log(y + 0.5)`` with smearing.

- **weights**: out-of-fold *optimal linear pool* — weights on the simplex that
  minimise the out-of-fold Poisson deviance of the weighted mean of member
  predictions (data-driven, non-degenerate, reported).

- **prediction** on the planning state space: the weighted mean (and the
  between-member spread). Because the LP bird row is a fixed coefficient per
  (development type, age), the ensemble is evaluated exactly via
  :func:`wbi_birds.bird.build_response_table` (no linear surrogate).

- **uncertainty**: draws of member coefficients from their covariance (the
  ensemble weights are held fixed; this is recorded in the report) produce one
  predictor per draw, from which per-draw response tables are built.

Nothing here imports R, SpaDES, or statsmodels/scikit-learn.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import digamma, gammaln

from wbi_birds.regression import (
    DEFAULT_FEATURES,
    RegressionError,
    fit_poisson_glm,
)

FAMILIES: tuple[str, ...] = ("poisson", "negbin", "poly_poisson", "loggauss")
DEFAULT_FAMILIES: tuple[str, ...] = ("poisson", "negbin", "poly_poisson")
POLY_FEATURE_NAMES: tuple[str, ...] = (
    "z_softwood",
    "z_hardwood",
    "z_age",
    "z_softwood2",
    "z_hardwood2",
    "z_age2",
    "z_softwood_hardwood",
    "z_softwood_age",
    "z_hardwood_age",
)


class EnsembleError(ValueError):
    """Raised when ensemble inputs are invalid or a member cannot be fitted."""


def _validate(raw: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(raw, dtype=float)
    yy = np.asarray(y, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(DEFAULT_FEATURES):
        raise EnsembleError("raw must be (n, 3): softwood, hardwood, age")
    if yy.ndim != 1 or yy.shape[0] != x.shape[0]:
        raise EnsembleError("response must be (n,) and match raw rows")
    if x.shape[0] < 10:
        raise EnsembleError("at least 10 observations are required")
    if np.any(yy < 0) or not np.all(np.isfinite(yy)):
        raise EnsembleError("counts must be finite and non-negative")
    if not np.all(np.isfinite(x)):
        raise EnsembleError("features must be finite")
    return x, yy


def _with_intercept(matrix: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((matrix.shape[0], 1)), matrix])


def _poly_expand(z: np.ndarray) -> np.ndarray:
    sw, hw, age = z[:, 0], z[:, 1], z[:, 2]
    return np.column_stack([sw, hw, age, sw * sw, hw * hw, age * age, sw * hw, sw * age, hw * age])


def _poisson_deviance(y: np.ndarray, mu: np.ndarray) -> float:
    mu = np.clip(mu, 1e-12, None)
    ratio = np.where(y > 0, y * np.log(np.where(y > 0, y, 1.0) / mu), 0.0)
    return float(2.0 * np.sum(ratio - (y - mu)))


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemberFit:
    """One fitted ensemble member (coefficients on the log scale unless noted)."""

    family: str
    feature_names: tuple[str, ...]
    beta: np.ndarray
    cov: np.ndarray
    center: np.ndarray | None = None
    scale: np.ndarray | None = None
    theta: float | None = None
    sigma2: float | None = None
    converged: bool = True

    def _design(self, raw: np.ndarray) -> np.ndarray:
        if self.family == "poly_poisson":
            assert self.center is not None and self.scale is not None
            z = (raw - self.center) / self.scale
            return _with_intercept(_poly_expand(z))
        return _with_intercept(raw)

    def mean(self, raw: np.ndarray, beta: np.ndarray | None = None) -> np.ndarray:
        """Expected count per row for raw state rows ``(n, 3)``."""
        x = self._design(np.atleast_2d(np.asarray(raw, dtype=float)))
        coef = self.beta if beta is None else beta
        eta = x @ coef
        if self.family == "loggauss":
            assert self.sigma2 is not None
            return np.clip(np.exp(np.clip(eta + self.sigma2 / 2.0, -30, 30)) - 0.5, 1e-8, None)
        return np.exp(np.clip(eta, -30.0, 30.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "features": list(self.feature_names),
            "beta": [float(v) for v in self.beta],
            "se": [float(v) for v in np.sqrt(np.clip(np.diag(self.cov), 0, None))],
            "theta": self.theta,
            "sigma2": self.sigma2,
            "converged": bool(self.converged),
        }


def _nb_nll_and_grad(params: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    beta = params[:-1]
    theta = math.exp(float(np.clip(params[-1], -20.0, 20.0)))
    eta = np.clip(x @ beta, -30.0, 30.0)
    mu = np.exp(eta)
    denom = theta + mu
    ll = (
        gammaln(y + theta)
        - gammaln(theta)
        - gammaln(y + 1.0)
        + theta * np.log(theta / denom)
        + y * np.log(mu / denom)
    )
    d_eta = theta * (y - mu) / denom
    d_theta = (
        digamma(y + theta)
        - digamma(theta)
        + np.log(theta)
        + 1.0
        - np.log(denom)
        - (theta + y) / denom
    )
    grad = np.concatenate([-(x.T @ d_eta), [-np.sum(d_theta) * theta]])
    return float(-np.sum(ll)), grad


def _numeric_hessian(fun_grad: Callable[[np.ndarray], np.ndarray], x0: np.ndarray) -> np.ndarray:
    k = x0.size
    hess = np.zeros((k, k))
    for j in range(k):
        step = 1e-5 * (abs(x0[j]) + 1.0)
        plus = x0.copy()
        minus = x0.copy()
        plus[j] += step
        minus[j] -= step
        hess[:, j] = (fun_grad(plus) - fun_grad(minus)) / (2.0 * step)
    return 0.5 * (hess + hess.T)


def _fit_negbin(raw: np.ndarray, y: np.ndarray) -> MemberFit:
    x = _with_intercept(raw)
    start = fit_poisson_glm(raw, y, DEFAULT_FEATURES)
    beta0 = np.array([start.coefficients[name] for name in ("intercept", *DEFAULT_FEATURES)])
    mu0 = np.exp(np.clip(x @ beta0, -30, 30))
    excess = max(float(np.mean((y - mu0) ** 2) - np.mean(mu0)), 1e-3)
    theta0 = float(np.clip(np.mean(mu0) ** 2 / excess, 1e-2, 1e4))
    params0 = np.concatenate([beta0, [math.log(theta0)]])
    result = minimize(
        _nb_nll_and_grad,
        params0,
        args=(x, y),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": 5000, "ftol": 1e-12, "gtol": 1e-8},
    )
    params = np.asarray(result.x, dtype=float)
    hess = _numeric_hessian(lambda p: _nb_nll_and_grad(p, x, y)[1], params)
    cov_full = np.linalg.pinv(hess)
    cov = cov_full[: beta0.size, : beta0.size]
    return MemberFit(
        family="negbin",
        feature_names=("intercept", *DEFAULT_FEATURES),
        beta=params[:-1],
        cov=cov,
        theta=float(math.exp(np.clip(params[-1], -20.0, 20.0))),
        converged=bool(result.success) or float(np.linalg.norm(result.jac)) < 1e-3,
    )


def _fit_poisson(raw: np.ndarray, y: np.ndarray) -> MemberFit:
    result = fit_poisson_glm(raw, y, DEFAULT_FEATURES)
    names = ("intercept", *DEFAULT_FEATURES)
    return MemberFit(
        family="poisson",
        feature_names=names,
        beta=np.array([result.coefficients[name] for name in names]),
        cov=np.asarray(result.covariance, dtype=float),
        converged=bool(result.converged),
    )


def _fit_poly(raw: np.ndarray, y: np.ndarray) -> MemberFit:
    center = raw.mean(axis=0)
    scale = raw.std(axis=0)
    scale[scale == 0.0] = 1.0
    expanded = _poly_expand((raw - center) / scale)
    result = fit_poisson_glm(expanded, y, POLY_FEATURE_NAMES)
    names = ("intercept", *POLY_FEATURE_NAMES)
    return MemberFit(
        family="poly_poisson",
        feature_names=names,
        beta=np.array([result.coefficients[name] for name in names]),
        cov=np.asarray(result.covariance, dtype=float),
        center=center,
        scale=scale,
        converged=bool(result.converged),
    )


def _fit_loggauss(raw: np.ndarray, y: np.ndarray) -> MemberFit:
    x = _with_intercept(raw)
    ylog = np.log(y + 0.5)
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ ylog
    resid = ylog - x @ beta
    dof = max(x.shape[0] - x.shape[1], 1)
    sigma2 = float(np.sum(resid**2) / dof)
    return MemberFit(
        family="loggauss",
        feature_names=("intercept", *DEFAULT_FEATURES),
        beta=beta,
        cov=sigma2 * xtx_inv,
        sigma2=sigma2,
    )


def fit_member(family: str, raw: np.ndarray, y: np.ndarray) -> MemberFit:
    """Fit a single ensemble member on raw state rows ``(n, 3)`` and counts ``(n,)``."""
    x, yy = _validate(raw, y)
    if family == "poisson":
        return _fit_poisson(x, yy)
    if family == "negbin":
        return _fit_negbin(x, yy)
    if family == "poly_poisson":
        return _fit_poly(x, yy)
    if family == "loggauss":
        return _fit_loggauss(x, yy)
    raise EnsembleError(f"unknown ensemble family '{family}' (expected one of {FAMILIES})")


# ---------------------------------------------------------------------------
# Weights and folds
# ---------------------------------------------------------------------------


def kfold_indices(n: int, folds: int, seed: int) -> list[np.ndarray]:
    """Deterministic k-fold partition of ``range(n)``."""
    if folds < 2 or folds > n:
        raise EnsembleError(f"folds must be in [2, n]; got {folds} for n={n}")
    rng = np.random.default_rng(seed)
    return [np.sort(part) for part in np.array_split(rng.permutation(n), folds)]


def optimal_pool_weights(oof: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Simplex weights minimising the out-of-fold Poisson deviance of the linear pool."""
    members = oof.shape[0]

    def objective(w: np.ndarray) -> float:
        mu = np.clip(w @ oof, 1e-12, None)
        return float(np.sum(mu - y * np.log(mu)))

    def gradient(w: np.ndarray) -> np.ndarray:
        mu = np.clip(w @ oof, 1e-12, None)
        return oof @ (1.0 - y / mu)

    start = np.full(members, 1.0 / members)
    result = minimize(
        objective,
        start,
        jac=gradient,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * members,
        constraints=[
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0, "jac": lambda w: np.ones(members)}
        ],
        options={"maxiter": 500, "ftol": 1e-12},
    )
    weights = np.clip(np.asarray(result.x, dtype=float), 0.0, None)
    total = weights.sum()
    return weights / total if total > 0 else start


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnsembleFit:
    """Fitted ensemble: members, out-of-fold weights and CV diagnostics."""

    members: tuple[MemberFit, ...]
    weights: np.ndarray
    cv_deviance: np.ndarray
    folds: int
    seed: int
    n: int
    notes: dict[str, Any] = field(default_factory=dict)

    def predict(self, raw: np.ndarray) -> np.ndarray:
        """Weighted-mean expected count for raw state rows ``(n, 3)``."""
        rows = np.atleast_2d(np.asarray(raw, dtype=float))
        means = np.vstack([member.mean(rows) for member in self.members])
        return self.weights @ means

    def spread(self, raw: np.ndarray) -> np.ndarray:
        """Between-member standard deviation of the expected count."""
        rows = np.atleast_2d(np.asarray(raw, dtype=float))
        means = np.vstack([member.mean(rows) for member in self.members])
        centre = self.weights @ means
        return np.sqrt(np.clip(self.weights @ (means - centre) ** 2, 0.0, None))

    def predictor(
        self, betas: Sequence[np.ndarray] | None = None
    ) -> Callable[[float, float, int], float]:
        """Scalar predictor ``(softwood, hardwood, age) -> value`` for state-space tables.

        ``betas`` optionally overrides each member's coefficients (one array per
        member, in member order) — used to evaluate coefficient draws.
        """
        members = self.members
        weights = self.weights

        def predict(softwood: float, hardwood: float, age: int) -> float:
            row = np.array([[float(softwood), float(hardwood), float(age)]])
            total = 0.0
            for index, member in enumerate(members):
                beta = None if betas is None else betas[index]
                total += float(weights[index]) * float(member.mean(row, beta)[0])
            return total

        return predict

    def draw_betas(self, n_draws: int, seed: int) -> list[list[np.ndarray]]:
        """Coefficient draws per member: ``draws[d][m]`` is member m's coefficients in draw d."""
        if n_draws < 1:
            raise EnsembleError("n_draws must be >= 1")
        rng = np.random.default_rng(seed)
        draws: list[list[np.ndarray]] = []
        factors = []
        for member in self.members:
            cov = 0.5 * (member.cov + member.cov.T)
            values, vectors = np.linalg.eigh(cov)
            root = vectors * np.sqrt(np.clip(values, 0.0, None))
            factors.append(root)
        for _ in range(n_draws):
            per_member = []
            for member, root in zip(self.members, factors, strict=True):
                noise = rng.standard_normal(member.beta.size)
                per_member.append(member.beta + root @ noise)
            draws.append(per_member)
        return draws

    def draw_predictors(
        self, n_draws: int, seed: int
    ) -> list[Callable[[float, float, int], float]]:
        """One scalar predictor per coefficient draw (weights held fixed)."""
        return [self.predictor(per_member) for per_member in self.draw_betas(n_draws, seed)]

    def report(self) -> dict[str, Any]:
        """JSON-serialisable fit report (members, weights, CV deviance, notes)."""
        return {
            "n": self.n,
            "folds": self.folds,
            "seed": self.seed,
            "members": [
                {
                    **member.to_dict(),
                    "weight": float(self.weights[index]),
                    "cv_deviance": float(self.cv_deviance[index]),
                }
                for index, member in enumerate(self.members)
            ],
            "weights_policy": "out-of-fold optimal linear pool (Poisson deviance, simplex)",
            "draw_policy": "member coefficients ~ N(beta, cov); ensemble weights fixed",
            **self.notes,
        }


def fit_ensemble(
    raw: np.ndarray,
    y: np.ndarray,
    families: Sequence[str] = DEFAULT_FAMILIES,
    *,
    folds: int = 5,
    seed: int = 0,
) -> EnsembleFit:
    """Fit the ensemble: out-of-fold member predictions, optimal pool weights, full refits."""
    x, yy = _validate(raw, y)
    families = tuple(families)
    if not families:
        raise EnsembleError("at least one ensemble family is required")
    for family in families:
        if family not in FAMILIES:
            raise EnsembleError(f"unknown ensemble family '{family}'")
    parts = kfold_indices(x.shape[0], folds, seed)
    oof = np.zeros((len(families), x.shape[0]))
    failures: dict[str, str] = {}
    for index, family in enumerate(families):
        for test in parts:
            train = np.setdiff1d(np.arange(x.shape[0]), test)
            try:
                member = fit_member(family, x[train], yy[train])
            except (RegressionError, EnsembleError, np.linalg.LinAlgError, ValueError) as exc:
                failures[family] = str(exc)
                oof[index, test] = float(np.mean(yy[train]))
                continue
            oof[index, test] = member.mean(x[test]).reshape(-1)
    cv_deviance = np.array(
        [_poisson_deviance(yy, oof[index]) / x.shape[0] for index in range(len(families))]
    )
    weights = optimal_pool_weights(oof, yy)
    members = tuple(fit_member(family, x, yy) for family in families)
    notes: dict[str, Any] = {"member_failures_in_cv": failures} if failures else {}
    return EnsembleFit(
        members=members,
        weights=weights,
        cv_deviance=cv_deviance,
        folds=folds,
        seed=seed,
        n=int(x.shape[0]),
        notes=notes,
    )
