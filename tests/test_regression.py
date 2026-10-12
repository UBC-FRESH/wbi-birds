from __future__ import annotations

import math

import numpy as np
import pytest

from wbi_birds.regression import (
    DEFAULT_FEATURES,
    INTERCEPT,
    RegressionError,
    aggregate_wood_types,
    correct_stand_age,
    design_matrix,
    expected_count,
    fit_poisson_glm,
    linear_predictor,
    scale_species_biomass,
    stepwise_aic,
)


def _simulate(n: int = 4000, seed: int = 11) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    rng = np.random.RandomState(seed)
    softwood = rng.uniform(5.0, 300.0, n)
    hardwood = rng.uniform(0.0, 60.0, n)
    age = rng.uniform(10.0, 200.0, n)
    truth = {INTERCEPT: 0.6, "softwood": 0.002, "hardwood": -0.006, "age": -0.0007}
    eta = (
        truth[INTERCEPT]
        + truth["softwood"] * softwood
        + truth["hardwood"] * hardwood
        + truth["age"] * age
    )
    counts = rng.poisson(np.exp(eta))
    return np.column_stack([softwood, hardwood, age]), counts, truth


def test_correct_stand_age_projects_and_drops() -> None:
    assert correct_stand_age(100.0, 2005) == 94.0  # 100 - (2011 - 2005)
    assert correct_stand_age(100.0, 2011) == 100.0
    assert correct_stand_age(100.0, 2015) == 104.0
    assert correct_stand_age(2.0, 2000) is None  # projects negative
    assert correct_stand_age(None, 2011) is None
    assert correct_stand_age(float("nan"), 2011) is None


def test_scale_species_biomass() -> None:
    assert scale_species_biomass(10.0, 100.0) == pytest.approx(0.01 * 10.0 * 100.0)
    assert scale_species_biomass(None, 100.0) == 0.0
    assert scale_species_biomass(10.0, None) == 0.0


def test_aggregate_wood_types() -> None:
    biomass = {"A": 10.0, "B": 5.0, "C": 2.0}
    soft, hard = aggregate_wood_types(
        biomass,
        softwood_species=("A", "B"),
        hardwood_species=("C",),
        merchantable_volume=100.0,
    )
    assert soft == pytest.approx(0.01 * 100.0 * 15.0)
    assert hard == pytest.approx(0.01 * 100.0 * 2.0)
    # no scaling when volume is omitted
    soft, hard = aggregate_wood_types(biomass, softwood_species=("A", "B"), hardwood_species=("C",))
    assert (soft, hard) == (15.0, 2.0)


def test_design_matrix_prepends_intercept() -> None:
    x = np.ones((3, 2))
    matrix, names = design_matrix(x, ("a", "b"))
    assert names == (INTERCEPT, "a", "b")
    assert matrix.shape == (3, 3)
    assert np.all(matrix[:, 0] == 1.0)
    with pytest.raises(RegressionError, match="column"):
        design_matrix(x, ("a",))


def test_fit_recovers_coefficients_with_statistics() -> None:
    features, counts, truth = _simulate()
    result = fit_poisson_glm(features, counts, DEFAULT_FEATURES)
    assert result.converged
    assert result.n == len(counts)
    for name, expected in truth.items():
        assert result.coefficients[name] == pytest.approx(expected, rel=0.15, abs=0.05)
        assert result.std_errors[name] > 0
        assert np.isfinite(result.p_values[name])
    assert result.p_values["softwood"] < 1e-6
    assert result.residual_deviance < result.null_deviance
    assert np.isfinite(result.aic)
    assert result.dispersion > 0
    payload = result.to_dict()
    assert payload["n"] == len(counts)
    assert "std_errors" in payload


def test_fit_rejects_invalid_response() -> None:
    features, counts, _ = _simulate(n=50)
    with pytest.raises(RegressionError, match="non-negative"):
        fit_poisson_glm(features, -counts, DEFAULT_FEATURES)


def test_stepwise_aic_drops_noise_predictor() -> None:
    features, counts, _ = _simulate()
    rng = np.random.RandomState(3)
    noise = rng.uniform(0.0, 1.0, features.shape[0])
    extended = np.column_stack([features, noise])
    selected, result = stepwise_aic(
        extended, counts, ("softwood", "hardwood", "age", "noise"), direction="backward"
    )
    assert "noise" not in selected
    assert set(selected) == {"softwood", "hardwood", "age"}
    assert result.converged


def test_stepwise_forward_selects_signal() -> None:
    features, counts, _ = _simulate(n=2000)
    selected, _result = stepwise_aic(
        features, counts, DEFAULT_FEATURES, direction="forward", max_steps=20
    )
    assert "softwood" in selected
    assert len(selected) >= 1


def test_linear_predictor_and_expected_count() -> None:
    coefficients = {INTERCEPT: 0.5, "swvol": 0.01, "hwvol": -0.02, "age": -0.001}
    features = {"swvol": 100.0, "hwvol": 10.0, "age": 80.0}
    eta = 0.5 + 0.01 * 100.0 - 0.02 * 10.0 - 0.001 * 80.0
    assert linear_predictor(coefficients, features) == pytest.approx(eta)
    assert expected_count(coefficients, features) == pytest.approx(math.exp(eta))
