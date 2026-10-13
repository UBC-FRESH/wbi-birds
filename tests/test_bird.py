from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

from wbi_birds import __version__
from wbi_birds.bird import (
    AnticipationCoefficients,
    bird_unit_value,
    build_response_table,
    compile_bird_row,
    load_bird_response,
    load_coefficients,
    state_space,
)
from wbi_birds.mapping import load_ws3_sections, stage_ws3_sections
from wbi_birds.model import build_model
from wbi_birds.responses import ResponseTable, ResponseTableError, write_response_tables
from wbi_birds.runner import ProblemSpec, run_scenario

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "femic_ws3_bundle"
INSTANCE_FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"
FIXTURE_MODEL = "tsa24_clipped"

PAPER_COEFFICIENTS = AnticipationCoefficients(
    swvol=2.181e-3, hwvol=-1.176e-2, age=-8.235e-4, intercept=7.594e-1
)


def _instance_with_bundle(tmp_path: Path) -> Path:
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    bundle = load_ws3_sections(FIXTURE_DIR, FIXTURE_MODEL)
    stage_ws3_sections(bundle, instance)
    return instance


def test_load_coefficients_from_fixture() -> None:
    coefficients = load_coefficients(INSTANCE_FIXTURE, "rebnut")
    assert coefficients.swvol > 0
    assert coefficients.hwvol < 0
    assert coefficients.age < 0


def test_bird_unit_value_identity(tmp_path: Path) -> None:
    model, _stats = build_model(_instance_with_bundle(tmp_path))
    for dtype_key in model.dtypes:
        development_type = model.dt(dtype_key)
        softwood = development_type.ycomp("swdvol")
        hardwood = development_type.ycomp("hwdvol")
        for age in (40, 80, 120):
            expected = (
                PAPER_COEFFICIENTS.swvol * softwood[age]
                + PAPER_COEFFICIENTS.hwvol * hardwood[age]
                + PAPER_COEFFICIENTS.age * age
                + PAPER_COEFFICIENTS.intercept
            )
            actual = bird_unit_value(model, dtype_key, age, PAPER_COEFFICIENTS)
            assert abs(actual - expected) < 1e-12


def test_bird_row_landscape_scenario(tmp_path: Path) -> None:
    model, _stats = build_model(_instance_with_bundle(tmp_path))
    spec = ProblemSpec(
        objective_expr="totvol * 0.85",
        constraint_row="bird_row",
        constraint_expr="bird",
        even_flow_epsilon=None,
        measure_scope="landscape",
        bird_coefficients=PAPER_COEFFICIENTS,
    )
    nadir = run_scenario(model, spec, scenario_id="tsa24-bird-00", management_unit="TSA24")
    assert nadir.status == "optimal", nadir.diagnostics
    assert nadir.bird_abundance_total is not None
    assert nadir.bird_abundance_total > 0
    assert len(nadir.bird_abundance_by_period) == 16
    assert nadir.provenance["measure_scope"] == "landscape"

    floor = {
        period: value * 0.95
        for period, value in enumerate(nadir.bird_abundance_by_period, start=1)
        if value > 0
    }
    floored = run_scenario(
        model,
        spec,
        scenario_id="tsa24-bird-05",
        management_unit="TSA24",
        constraint_floor=floor,
    )
    assert floored.status == "optimal", floored.diagnostics
    for period, value in floor.items():
        assert floored.bird_abundance_by_period[period - 1] >= value - 1e-6
    assert floored.harvest_volume_total_m3 is not None
    tolerance = max(1.0, 1e-6 * nadir.harvest_volume_total_m3)
    assert floored.harvest_volume_total_m3 <= nadir.harvest_volume_total_m3 + tolerance


def test_bird_row_matches_manual_sum(tmp_path: Path) -> None:
    model, _stats = build_model(_instance_with_bundle(tmp_path))
    spec = ProblemSpec(
        objective_expr="totvol * 0.85",
        constraint_row="bird_row",
        constraint_expr="bird",
        even_flow_epsilon=None,
        measure_scope="landscape",
        bird_coefficients=PAPER_COEFFICIENTS,
    )
    result = run_scenario(model, spec, scenario_id="tsa24-bird-manual", management_unit="TSA24")
    assert result.status == "optimal", result.diagnostics

    manual: list[float] = []
    for period in model.periods:
        total = 0.0
        for acode in ("null", "harvest"):
            for dtype_key, ages in model.applied_actions[period][acode].items():
                for age, slot in ages.items():
                    if slot[0] > 0:
                        total += slot[0] * bird_unit_value(
                            model, dtype_key, int(age), PAPER_COEFFICIENTS
                        )
        manual.append(total)
    series = compile_bird_row(model, PAPER_COEFFICIENTS, acodes=("null", "harvest"))
    assert len(series) == len(manual)
    for a, b in zip(series, manual, strict=True):
        assert abs(a - b) < 1e-9
    assert any(value > 0 for value in series)


def test_build_response_table_exact_nonlinear(fixture_model) -> None:
    """A non-linear fitted response is reproduced exactly on the state space."""
    model = fixture_model
    ages = (40, 80, 120)

    def predict(softwood: float, hardwood: float, age: int) -> float:
        return 1.5 + 0.01 * softwood + 0.02 * hardwood + math.exp(-age / 100.0)

    table = build_response_table(
        model,
        "rebnut",
        predict,
        ages=ages,
        sd=lambda *_: 0.3,
        source={"fit": "test"},
        acodes=("null", "harvest"),
    )
    assert table.species_code == "rebnut"
    assert table.values  # reachable states were materialised and evaluated
    for dtype_key, age in table.values:
        development_type = model.dt(dtype_key)
        softwood = development_type.ycomp("swdvol")[age]
        hardwood = development_type.ycomp("hwdvol")[age]
        assert bird_unit_value(model, dtype_key, age, table) == predict(softwood, hardwood, age)
        assert table.unit_sd(dtype_key, age) == 0.3


def test_state_space_restricted_and_invalid_age(fixture_model) -> None:
    model = fixture_model
    pairs = state_space(model, ages=[0, 40])
    assert len(pairs) == len(model.dtypes) * 2
    with pytest.raises(ValueError, match="not in the yield curves"):
        state_space(model, ages=[9999])


def test_load_bird_response_prefers_table(tmp_path: Path) -> None:
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    dtype = ("dt", "0", "1", "1", "1")
    write_response_tables(
        instance / "bird" / "response_table.csv",
        [ResponseTable(species_code="rebnut", values={(dtype, 80): 12.5})],
    )
    assert isinstance(load_bird_response(instance, "rebnut"), ResponseTable)
    assert isinstance(load_bird_response(instance, "borchi2"), AnticipationCoefficients)


def test_bird_row_response_table_scenario(fixture_model) -> None:
    """A response-table row solves end-to-end and records its provenance."""
    model = fixture_model
    table = build_response_table(
        model,
        "rebnut",
        lambda sw, hw, age: 0.5 + 0.001 * sw - 0.002 * hw + 1e-4 * age,
        acodes=("null", "harvest"),
    )
    spec = ProblemSpec(
        objective_expr="totvol * 0.85",
        constraint_row="bird_row",
        constraint_expr="bird",
        even_flow_epsilon=None,
        measure_scope="landscape",
        bird_coefficients=table,
    )
    result = run_scenario(model, spec, scenario_id="tsa24-bird-rt", management_unit="TSA24")
    assert result.status == "optimal", result.diagnostics
    assert result.provenance["bird_response"]["species_code"] == "rebnut"


def test_build_response_table_requires_states_or_acodes(fixture_model) -> None:
    with pytest.raises(ValueError, match="needs states or acodes"):
        build_response_table(fixture_model, "rebnut", lambda sw, hw, age: 1.0)


def test_build_response_table_rejects_non_finite_predictions(fixture_model) -> None:
    with pytest.raises(ResponseTableError, match="Non-finite predicted value"):
        build_response_table(
            fixture_model, "rebnut", lambda sw, hw, age: math.nan, acodes=("null", "harvest")
        )


def test_build_response_table_records_engine_version(fixture_model) -> None:
    table = build_response_table(
        fixture_model, "rebnut", lambda sw, hw, age: 1.0, acodes=("null", "harvest")
    )
    assert table.source["engine_version"] == __version__
