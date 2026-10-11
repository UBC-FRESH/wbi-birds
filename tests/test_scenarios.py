from __future__ import annotations

import pytest
from pydantic import ValidationError

from wbi_birds.scenarios import (
    EvenFlowConfig,
    ScenarioResult,
    ScenarioSet,
    ScenarioSpec,
    SolverResult,
    dump_yaml,
    load_yaml,
)


def _spec(scenario_id: str = "tsa40-rebnut-s00", level: float = 0.0, floor: float | None = None):
    return ScenarioSpec(
        id=scenario_id,
        management_unit="TSA40",
        species=["rebnut"],
        epsilon_level=level,
        bird_abundance_floor=floor,
        horizon_years=80,
        utilization=0.85,
        even_flow=EvenFlowConfig(epsilon=0.10),
    )


def test_scenario_spec_round_trip_dict() -> None:
    spec = _spec()
    assert ScenarioSpec.model_validate(spec.model_dump()) == spec


def test_scenario_spec_round_trip_json() -> None:
    spec = _spec(level=0.5, floor=123.4)
    assert ScenarioSpec.model_validate_json(spec.model_dump_json()) == spec


def test_scenario_spec_round_trip_yaml() -> None:
    spec = _spec(level=1.0, floor=999.0)
    assert load_yaml(dump_yaml(spec), ScenarioSpec) == spec


def test_scenario_set_round_trip_yaml() -> None:
    scenario_set = ScenarioSet(
        management_unit="TSA40",
        species=["rebnut"],
        scenarios=[
            _spec("tsa40-rebnut-s00", 0.0),
            _spec("tsa40-rebnut-s05", 0.5, 500.0),
            _spec("tsa40-rebnut-s10", 1.0, 1000.0),
        ],
    )
    assert load_yaml(dump_yaml(scenario_set), ScenarioSet) == scenario_set


def test_scenario_set_rejects_unordered_levels() -> None:
    with pytest.raises(ValidationError):
        ScenarioSet(
            management_unit="TSA40",
            species=["rebnut"],
            scenarios=[_spec("tsa40-rebnut-s05", 0.5), _spec("tsa40-rebnut-s00", 0.0)],
        )


def test_scenario_set_rejects_management_unit_mismatch() -> None:
    other = _spec("tsa16-rebnut-s00", 0.0).model_copy(update={"management_unit": "TSA16"})
    with pytest.raises(ValidationError):
        ScenarioSet(management_unit="TSA40", species=["rebnut"], scenarios=[other])


def test_scenario_set_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        ScenarioSet(
            management_unit="TSA40",
            species=["rebnut"],
            scenarios=[_spec("tsa40-rebnut-s00", 0.0), _spec("tsa40-rebnut-s00", 0.5)],
        )


def test_scenario_spec_rejects_invalid_level() -> None:
    with pytest.raises(ValidationError):
        _spec(level=1.5)


def test_scenario_spec_rejects_unknown_solver() -> None:
    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate({**_spec().model_dump(), "solver": {"backend": "cplex"}})


def test_scenario_spec_rejects_empty_species() -> None:
    with pytest.raises(ValidationError):
        ScenarioSpec(
            id="tsa40-s00",
            management_unit="TSA40",
            species=[],
            epsilon_level=0.0,
            horizon_years=80,
            utilization=0.85,
            even_flow=EvenFlowConfig(epsilon=0.10),
        )


def test_scenario_result_round_trip() -> None:
    result = ScenarioResult(
        scenario_id="tsa40-rebnut-s10",
        management_unit="TSA40",
        status="optimal",
        harvest_volume_m3_by_period=[1.0, 2.0, 3.0],
        bird_abundance_by_period=[4.0, 5.0, 6.0],
        harvest_volume_total_m3=6.0,
        bird_abundance_total=15.0,
        solver=SolverResult(backend="highs", status_raw="Optimal", runtime_seconds=2.44),
        artifacts={"results": "results/scenarios/TSA40/rebnut/s10.csv"},
        diagnostics=[],
        engine_version="0.1.0a1",
    )
    assert ScenarioResult.model_validate(result.model_dump()) == result
    assert load_yaml(dump_yaml(result), ScenarioResult) == result
