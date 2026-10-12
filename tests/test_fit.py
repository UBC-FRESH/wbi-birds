from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from wbi_birds.bird import AnticipationCoefficients, load_bird_response, load_coefficients
from wbi_birds.fit import (
    FitError,
    fit_and_stage,
    fit_poisson_glm,
    make_covariates_csv,
    stage_coefficients,
    stage_response_table,
    update_instance_coefficients,
)
from wbi_birds.responses import ResponseTable

INSTANCE_FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"

TRUE_COEFFICIENTS = AnticipationCoefficients(intercept=0.7, swvol=0.0021, hwvol=-0.011, age=-0.0008)


def _instance(tmp_path: Path) -> Path:
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    return instance


def _synthetic_covariates(tmp_path: Path, n: int = 2000) -> Path:
    rng = np.random.RandomState(7)
    swvol = rng.uniform(5.0, 300.0, n)
    hwvol = rng.uniform(0.0, 60.0, n)
    age = rng.uniform(10.0, 150.0, n)
    eta = (
        TRUE_COEFFICIENTS.intercept
        + TRUE_COEFFICIENTS.swvol * swvol
        + TRUE_COEFFICIENTS.hwvol * hwvol
        + TRUE_COEFFICIENTS.age * age
    )
    counts = rng.poisson(np.exp(eta))
    return make_covariates_csv(
        list(zip(swvol, hwvol, age, strict=True)), list(counts), tmp_path / "covariates.csv"
    )


def test_fit_poisson_glm_recovers_synthetic_coefficients(tmp_path: Path) -> None:
    covariates = _synthetic_covariates(tmp_path)
    result = fit_poisson_glm(covariates)
    assert result.converged
    assert result.n_observations == 2000
    fitted = result.coefficients
    assert abs(fitted.swvol - TRUE_COEFFICIENTS.swvol) < 0.3 * abs(TRUE_COEFFICIENTS.swvol)
    assert abs(fitted.hwvol - TRUE_COEFFICIENTS.hwvol) < 0.3 * abs(TRUE_COEFFICIENTS.hwvol)
    assert abs(fitted.intercept - TRUE_COEFFICIENTS.intercept) < 0.3
    assert "coefficients" in result.to_dict()


def test_fit_poisson_glm_rejects_bad_table(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("observation_count,swvol\n1,10\n", encoding="utf-8")
    with pytest.raises(FitError, match="missing column"):
        fit_poisson_glm(bad)


def test_stage_coefficients_validates_and_writes(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    source = tmp_path / "provided.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "source": {"ebd_release": "ebd_test", "fit_script": "r-lineage"},
                "species": {
                    "rebnut": {"intercept": 0.5, "swvol": 0.002, "hwvol": -0.01, "age": -0.0008},
                    "borchi2": {"intercept": 0.4, "swvol": 0.001, "hwvol": -0.004, "age": -0.0003},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    path = stage_coefficients(source, instance)
    assert path == instance / "bird" / "coefficients.yaml"
    loaded = load_coefficients(instance, "rebnut")
    assert loaded.intercept == 0.5
    payload = yaml.safe_load(path.read_text())
    assert payload["source"]["fit"] == "provided"
    assert payload["source"]["ebd_release"] == "ebd_test"
    assert list(payload["species"]) == ["borchi2", "rebnut"]  # sorted, deterministic


def test_stage_coefficients_rejects_unknown_code(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    source = tmp_path / "bad.yaml"
    source.write_text(
        yaml.safe_dump(
            {"species": {"notabird": {"intercept": 0, "swvol": 0, "hwvol": 0, "age": 0}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(FitError, match="Unknown species code"):
        stage_coefficients(source, instance)


def test_fit_and_stage_preserves_other_species(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    covariates = _synthetic_covariates(tmp_path)
    result, path = fit_and_stage(covariates, instance, "rebnut")
    assert result.converged
    payload = yaml.safe_load(path.read_text())
    assert payload["source"]["fit"] == "poisson_mle"
    assert "borchi2" in payload["species"]  # preserved from the fixture
    fitted = load_coefficients(instance, "rebnut")
    assert abs(fitted.swvol - TRUE_COEFFICIENTS.swvol) < 0.3 * abs(TRUE_COEFFICIENTS.swvol)


def test_update_instance_coefficients_creates_missing_file(tmp_path: Path) -> None:
    instance = tmp_path / "instance"
    (instance / "bird").mkdir(parents=True)
    path = update_instance_coefficients(
        instance,
        "rebnut",
        AnticipationCoefficients(intercept=1.0, swvol=0.001, hwvol=-0.002, age=-0.0004),
        fit_note="poisson_mle",
    )
    assert path.is_file()
    assert load_coefficients(instance, "rebnut").intercept == 1.0


def test_stage_response_table_round_trip(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    dtype = ("dt", "0", "1", "1", "1")
    table = ResponseTable(species_code="rebnut", values={(dtype, 80): 12.5})
    path = stage_response_table(instance, table)
    assert path.is_file()
    loaded = load_bird_response(instance, "rebnut")
    assert isinstance(loaded, ResponseTable)
    assert loaded.unit_value(dtype, 80) == 12.5
    assert loaded.source["fit"] == "provided"
    # other species still fall back to coefficients
    assert isinstance(load_bird_response(instance, "borchi2"), AnticipationCoefficients)


def test_stage_response_table_unknown_species(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    table = ResponseTable(species_code="nope1", values={(("dt",), 1): 1.0})
    with pytest.raises(FitError, match="Unknown species code"):
        stage_response_table(instance, table)
