from __future__ import annotations

import json
from pathlib import Path

from wbi_birds.b3 import interpolate_harvest, run_b3_comparison, write_b3_result
from wbi_birds.model import build_model
from wbi_birds.reserves import (
    IMPOSSIBLE_EXPR,
    apply_reserve_exclusion,
    select_reserves_by_min_age,
)
from wbi_birds.runner import ProblemSpec, run_scenario

SPEC = ProblemSpec(
    objective_expr="totvol * 0.85",
    constraint_row="prod",
    constraint_expr="totvol",
    even_flow_epsilon=None,
)


def test_select_reserves_by_min_age(fixture_instance: Path) -> None:
    model, _ = build_model(fixture_instance)
    selection = select_reserves_by_min_age(model, 80)
    assert 0 < len(selection.dtype_keys) < len(model.dtypes)
    assert selection.criterion == "initial_age>=80"


def test_reserve_exclusion_reduces_harvest(fixture_instance: Path) -> None:
    baseline_model, _ = build_model(fixture_instance)
    baseline = run_scenario(baseline_model, SPEC, scenario_id="tsa24-base", management_unit="TSA24")
    assert baseline.status == "optimal", baseline.diagnostics

    model, _ = build_model(fixture_instance)
    selection = select_reserves_by_min_age(model, 80)
    key = selection.dtype_keys[0]
    apply_reserve_exclusion(model, selection)
    assert model.dtypes[key].oper_expr["harvest"] == [IMPOSSIBLE_EXPR]

    excluded = run_scenario(model, SPEC, scenario_id="tsa24-reserve", management_unit="TSA24")
    assert excluded.status == "optimal", excluded.diagnostics
    assert excluded.harvest_volume_total_m3 < baseline.harvest_volume_total_m3


def test_interpolate_harvest() -> None:
    frontier = [
        {"status": "optimal", "bird_abundance_total": 100.0, "harvest_volume_total_m3": 1000.0},
        {"status": "optimal", "bird_abundance_total": 200.0, "harvest_volume_total_m3": 500.0},
    ]
    assert interpolate_harvest(frontier, 150.0) == 750.0
    assert interpolate_harvest(frontier, 50.0) is None


def test_b3_comparison_smoke(fixture_instance: Path, tmp_path: Path) -> None:
    integrated, _ = build_model(fixture_instance)
    sequential, _ = build_model(fixture_instance)
    selection = select_reserves_by_min_age(integrated, 80)

    nadir = run_scenario(integrated, SPEC, scenario_id="tsa24-int-nadir", management_unit="TSA24")
    assert nadir.status == "optimal", nadir.diagnostics
    floor = {
        period: value * 0.5
        for period, value in enumerate(nadir.bird_abundance_by_period, start=1)
        if value > 0
    }

    b3 = run_b3_comparison(
        integrated,
        sequential,
        SPEC,
        selection,
        management_unit="TSA24",
        floors=(None, floor),
    )

    assert b3.sequential["status"] == "optimal", b3.sequential
    assert b3.reserve["dtype_count"] > 0
    assert len(b3.integrated_frontier) == 2
    assert all(entry["status"] == "optimal" for entry in b3.integrated_frontier)
    assert b3.matched["bird_target"] is not None
    assert "harvest_integrated_m3" in b3.matched
    if b3.matched["harvest_integrated_m3"] is None:
        assert "note" in b3.matched
    else:
        assert "reserve_penalty_m3" in b3.matched

    path = write_b3_result(b3, tmp_path / "results")
    assert path.is_file()
    payload = json.loads(path.read_text())
    assert payload["management_unit"] == "TSA24"
    assert payload["matched"]["bird_target"] == b3.matched["bird_target"]
