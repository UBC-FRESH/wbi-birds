from __future__ import annotations

import shutil
from pathlib import Path

from wbi_birds.mapping import load_ws3_sections, stage_ws3_sections
from wbi_birds.model import build_model
from wbi_birds.runner import ProblemSpec, ScenarioRunError, run_scenario

FIXTURE = Path(__file__).parent / "fixtures" / "femic_ws3_bundle"
INSTANCE_FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"
MODEL = "tsa24_clipped"

SPEC_NO_FLOW = ProblemSpec(
    objective_expr="totvol * 0.85",
    constraint_row="prod",
    constraint_expr="totvol",
    even_flow_epsilon=None,
)


def _build(tmp_path: Path):
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    bundle = load_ws3_sections(FIXTURE, MODEL)
    stage_ws3_sections(bundle, instance)
    model, _stats = build_model(instance)
    return model


def test_run_scenario_nadir(tmp_path: Path) -> None:
    model = _build(tmp_path)
    result = run_scenario(model, SPEC_NO_FLOW, scenario_id="tsa24-s00", management_unit="TSA24")
    assert result.status == "optimal", result.diagnostics
    assert result.harvest_volume_total_m3 is not None
    assert result.harvest_volume_total_m3 > 0
    assert len(result.harvest_volume_m3_by_period) == 16
    assert len(result.bird_abundance_by_period) == 16
    assert result.solver.backend == "highs"
    assert result.solver.status_raw
    assert "objective_value" in result.provenance


def test_run_scenario_with_constraint_floor(tmp_path: Path) -> None:
    model = _build(tmp_path)
    nadir = run_scenario(model, SPEC_NO_FLOW, scenario_id="tsa24-s00", management_unit="TSA24")
    assert nadir.bird_abundance_total is not None
    # per-period floor: 90% of the nadir schedule's first-period output (feasible by construction)
    floor = {1: nadir.bird_abundance_by_period[0] * 0.9}
    result = run_scenario(
        model,
        SPEC_NO_FLOW,
        scenario_id="tsa24-s05",
        management_unit="TSA24",
        constraint_floor=floor,
    )
    assert result.status == "optimal", result.diagnostics
    assert result.bird_abundance_by_period[0] >= floor[1] - 1e-6
    assert result.harvest_volume_total_m3 is not None
    tolerance = max(1.0, 1e-6 * nadir.harvest_volume_total_m3)
    assert result.harvest_volume_total_m3 <= nadir.harvest_volume_total_m3 + tolerance


def test_run_scenario_infeasible_floor(tmp_path: Path) -> None:
    model = _build(tmp_path)
    result = run_scenario(
        model,
        SPEC_NO_FLOW,
        scenario_id="tsa24-s99",
        management_unit="TSA24",
        constraint_floor=1e12,
    )
    assert result.status in ("infeasible", "error")
    assert result.harvest_volume_total_m3 is None


def test_run_scenario_even_flow(tmp_path: Path) -> None:
    model = _build(tmp_path)
    spec = ProblemSpec(
        objective_expr="totvol * 0.85",
        constraint_row="prod",
        constraint_expr="totvol",
        even_flow_epsilon=0.9,
    )
    result = run_scenario(model, spec, scenario_id="tsa24-flow", management_unit="TSA24")
    assert result.status == "optimal", result.diagnostics
    assert result.harvest_volume_total_m3 is not None
    assert result.harvest_volume_total_m3 > 0


def test_run_scenario_bird_objective(tmp_path: Path) -> None:
    from wbi_birds.bird import load_coefficients

    model = _build(tmp_path)
    coefficients = load_coefficients(INSTANCE_FIXTURE, "rebnut")
    harvest_spec = ProblemSpec(
        objective_expr="totvol * 0.85",
        constraint_row="prod",
        constraint_expr="totvol",
        even_flow_epsilon=None,
        bird_coefficients=coefficients,
    )
    nadir = run_scenario(model, harvest_spec, scenario_id="tsa24-s00", management_unit="TSA24")
    assert nadir.status == "optimal", nadir.diagnostics
    assert nadir.bird_abundance_total is not None

    bird_spec = ProblemSpec(
        objective_expr="bird",
        constraint_row="prod",
        constraint_expr="totvol",
        even_flow_epsilon=None,
        bird_coefficients=coefficients,
    )
    result = run_scenario(model, bird_spec, scenario_id="tsa24-bmax", management_unit="TSA24")
    assert result.status == "optimal", result.diagnostics
    assert result.bird_abundance_total is not None
    assert result.bird_abundance_total >= nadir.bird_abundance_total - 1e-6


def test_run_scenario_bird_objective_requires_flow_expr(tmp_path: Path) -> None:
    from wbi_birds.bird import load_coefficients

    model = _build(tmp_path)
    coefficients = load_coefficients(INSTANCE_FIXTURE, "rebnut")
    spec = ProblemSpec(
        objective_expr="bird",
        constraint_row="prod",
        constraint_expr="totvol",
        even_flow_epsilon=0.1,
        bird_coefficients=coefficients,
    )
    try:
        run_scenario(model, spec, scenario_id="tsa24-bmax", management_unit="TSA24")
    except ScenarioRunError as exc:
        assert "flow_expr" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ScenarioRunError")
