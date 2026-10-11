from __future__ import annotations

import shutil
from pathlib import Path

from wbi_birds.bird import (
    AnticipationCoefficients,
    bird_unit_value,
    compile_bird_row,
    load_coefficients,
)
from wbi_birds.mapping import load_ws3_sections, stage_ws3_sections
from wbi_birds.model import build_model
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
