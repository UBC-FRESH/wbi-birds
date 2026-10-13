from __future__ import annotations

import math

import pytest

from wbi_birds.regression import PoissonFitResult, quasi_poisson_summary


def _fit(residual_deviance: float) -> PoissonFitResult:
    return PoissonFitResult(
        coefficients={"intercept": 0.5, "age": -0.01},
        std_errors={"intercept": 0.1, "age": 0.002},
        z_values={"intercept": 5.0, "age": -5.0},
        p_values={"intercept": 0.0, "age": 0.0},
        n=100,
        null_deviance=200.0,
        residual_deviance=residual_deviance,
        log_likelihood=-50.0,
        aic=110.0,
        converged=True,
    )


def test_quasi_poisson_scales_standard_errors_by_root_dispersion() -> None:
    result = _fit(residual_deviance=4.0 * 98)  # dispersion = residual deviance / (n - p) = 4
    assert result.dispersion == pytest.approx(4.0)
    summary = quasi_poisson_summary(result)
    assert summary["std_errors"]["intercept"] == pytest.approx(0.2)
    assert summary["std_errors"]["age"] == pytest.approx(0.004)
    assert summary["z_values"]["intercept"] == pytest.approx(2.5)
    assert summary["z_values"]["age"] == pytest.approx(-2.5)
    assert summary["p_values"]["intercept"] == pytest.approx(math.erfc(2.5 / math.sqrt(2.0)))


def test_unit_dispersion_leaves_standard_errors_unchanged() -> None:
    summary = quasi_poisson_summary(_fit(residual_deviance=98.0))
    assert summary["std_errors"]["age"] == pytest.approx(0.002)


def test_quasi_poisson_rejects_non_positive_dispersion() -> None:
    with pytest.raises(ValueError, match="dispersion"):
        quasi_poisson_summary(_fit(residual_deviance=0.0))
