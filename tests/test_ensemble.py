from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from wbi_birds.ensemble import (
    EnsembleError,
    fit_ensemble,
    fit_member,
    kfold_indices,
    optimal_pool_weights,
)

FIXTURE_INSTANCE = Path(__file__).parent / "fixtures" / "instance_valid"


def _poisson_data(n: int = 2500, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    sw = rng.uniform(0, 300, n)
    hw = rng.uniform(0, 60, n)
    age = rng.uniform(10, 200, n)
    eta = 0.6 + 0.002 * sw - 0.006 * hw - 0.0007 * age
    return np.column_stack([sw, hw, age]), rng.poisson(np.exp(eta))


def _negbin_data(
    n: int = 4000, seed: int = 11, theta: float = 1.5
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    sw = rng.uniform(0, 300, n)
    hw = rng.uniform(0, 60, n)
    age = rng.uniform(10, 200, n)
    mu = np.exp(0.6 + 0.002 * sw - 0.006 * hw - 0.0007 * age)
    lam = rng.gamma(shape=theta, scale=mu / theta)
    return np.column_stack([sw, hw, age]), rng.poisson(lam)


def test_kfold_partition_is_complete_and_deterministic() -> None:
    parts = kfold_indices(103, 5, seed=4)
    assert sorted(np.concatenate(parts).tolist()) == list(range(103))
    again = kfold_indices(103, 5, seed=4)
    assert all(np.array_equal(a, b) for a, b in zip(parts, again, strict=True))
    with pytest.raises(EnsembleError):
        kfold_indices(10, 1, seed=0)


def test_negbin_recovers_dispersion() -> None:
    raw, y = _negbin_data()
    member = fit_member("negbin", raw, y)
    assert member.converged
    assert member.theta == pytest.approx(1.5, rel=0.3)
    # Each coefficient lies within ~3 standard errors of the truth (sampling error, not bias).
    se = np.sqrt(np.diag(member.cov))
    truth = np.array([0.6, 0.002, -0.006, -0.0007])
    assert np.all(np.abs(member.beta - truth) < 3.0 * se)


def test_poisson_member_matches_regression_fit() -> None:
    raw, y = _poisson_data()
    member = fit_member("poisson", raw, y)
    assert member.beta[1] == pytest.approx(0.002, rel=0.1)
    assert np.all(np.isfinite(member.cov))


def test_optimal_pool_prefers_the_better_member() -> None:
    rng = np.random.default_rng(3)
    y = rng.poisson(2.0, 400).astype(float)
    good = np.full(400, 2.0)
    bad = np.full(400, 0.2)
    weights = optimal_pool_weights(np.vstack([good, bad]), y)
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights >= 0)
    assert weights[0] > 0.9


def test_fit_ensemble_weights_and_prediction() -> None:
    raw, y = _poisson_data()
    ens = fit_ensemble(raw, y, ("poisson", "negbin", "poly_poisson", "loggauss"), folds=5, seed=1)
    assert ens.weights.sum() == pytest.approx(1.0)
    assert np.all(ens.weights >= 0)
    assert len(ens.cv_deviance) == 4
    pred = ens.predict(raw[:20])
    assert pred.shape == (20,) and np.all(np.isfinite(pred)) and np.all(pred > 0)
    spread = ens.spread(raw[:20])
    assert np.all(spread >= 0)
    report = ens.report()
    assert report["folds"] == 5 and len(report["members"]) == 4


def test_overdispersed_data_shift_weight_to_negbin() -> None:
    raw, y = _negbin_data()
    ens = fit_ensemble(raw, y, ("poisson", "negbin"), folds=5, seed=2)
    names = [member.family for member in ens.members]
    assert ens.weights[names.index("negbin")] > 0.8
    assert ens.cv_deviance[names.index("negbin")] <= ens.cv_deviance[names.index("poisson")]


def test_scalar_predictor_matches_vector_prediction() -> None:
    raw, y = _poisson_data()
    ens = fit_ensemble(raw, y, ("poisson", "poly_poisson"), folds=4, seed=0)
    predictor = ens.predictor()
    row = np.array([[100.0, 10.0, 80.0]])
    assert predictor(100.0, 10.0, 80) == pytest.approx(float(ens.predict(row)[0]))


def test_coefficient_draws_are_reproducible_and_bracket_the_point_fit() -> None:
    raw, y = _poisson_data()
    ens = fit_ensemble(raw, y, ("poisson", "poly_poisson"), folds=4, seed=0)
    first = ens.draw_betas(40, seed=9)
    again = ens.draw_betas(40, seed=9)
    assert all(
        np.array_equal(a, b)
        for d1, d2 in zip(first, again, strict=True)
        for a, b in zip(d1, d2, strict=True)
    )
    values = np.array([pred(100.0, 10.0, 80) for pred in ens.draw_predictors(60, seed=9)])
    point = ens.predictor()(100.0, 10.0, 80)
    assert values.std() > 0
    assert (
        values.min() <= point <= values.max() or abs(np.median(values) - point) < 3 * values.std()
    )


def test_invalid_inputs_are_rejected() -> None:
    raw, y = _poisson_data(n=50)
    with pytest.raises(EnsembleError):
        fit_ensemble(raw, -y, ("poisson",), folds=3)
    with pytest.raises(EnsembleError):
        fit_ensemble(raw, y, ("not_a_family",), folds=3)
    with pytest.raises(EnsembleError):
        fit_member("poisson", raw[:, :2], y)


def test_state_space_table_reproduces_the_ensemble(fixture_model) -> None:
    """The ensemble, evaluated on the planning state space, equals the response table."""
    from wbi_birds.bird import build_response_table, reachable_state_space

    raw, y = _poisson_data(n=600)
    ens = fit_ensemble(raw, y, ("poisson", "poly_poisson"), folds=4, seed=0)
    states = reachable_state_space(fixture_model, ages=(40, 80, 120))
    table = build_response_table(fixture_model, "rebnut", ens.predictor(), states=states)
    checked = 0
    for (dtype_key, age), value in list(table.values.items())[:25]:
        development_type = fixture_model.dt(dtype_key)
        softwood = development_type.ycomp("swdvol")[age]
        hardwood = development_type.ycomp("hwdvol")[age]
        expected = float(ens.predict(np.array([[softwood, hardwood, age]]))[0])
        assert value == pytest.approx(expected)
        checked += 1
    assert checked > 0


def test_stage_ensemble_response_writes_table_report_and_draws(fixture_model, tmp_path) -> None:
    import json
    import shutil

    from wbi_birds.bird import reachable_state_space
    from wbi_birds.fit import stage_ensemble_response
    from wbi_birds.responses import load_response_table, read_response_tables

    instance = tmp_path / "staged-instance"
    shutil.copytree(FIXTURE_INSTANCE, instance)
    raw, y = _poisson_data(n=600)
    ens = fit_ensemble(raw, y, ("poisson", "poly_poisson"), folds=4, seed=0)
    states = reachable_state_space(fixture_model, ages=(40, 80))
    stage_ensemble_response(
        fixture_model, "rebnut", ens, instance, states=states, draws=3, draw_seed=5
    )

    table = load_response_table(instance, "rebnut")
    assert table.source["fit"] == "ensemble"
    assert len(table.values) == len(states)

    report = json.loads((instance / "bird" / "fit_report.json").read_text(encoding="utf-8"))
    assert report["species_code"] == "rebnut"
    assert report["draws"] == 3
    assert len(report["members"]) == 2

    draw_files = sorted((instance / "bird" / "draws").glob("rebnut_draw*.csv"))
    assert len(draw_files) == 3
    first_draw = read_response_tables(draw_files[0])["rebnut"]
    assert len(first_draw.values) == len(states)
    assert first_draw.values != table.values  # draws genuinely perturb the point fit
