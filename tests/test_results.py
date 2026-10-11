from __future__ import annotations

import csv
from pathlib import Path

from wbi_birds.results import TABLE_COLUMNS, load_scenario_result, write_scenario_result
from wbi_birds.runner import ProblemSpec, run_scenario

SPEC = ProblemSpec(
    objective_expr="totvol * 0.85",
    constraint_row="prod",
    constraint_expr="totvol",
    even_flow_epsilon=None,
)


def _run(fixture_model):
    return run_scenario(
        fixture_model,
        SPEC,
        scenario_id="tsa24-s00",
        management_unit="TSA24",
    )


def test_write_scenario_result(fixture_model, tmp_path: Path) -> None:
    result = _run(fixture_model)
    assert result.status == "optimal", result.diagnostics
    root = tmp_path / "results"

    updated = write_scenario_result(result, root)

    table_path = root / "scenarios" / "tsa24" / "tsa24-s00.csv"
    record_path = root / "scenarios" / "tsa24" / "tsa24-s00.result.yaml"
    assert table_path.is_file()
    assert record_path.is_file()
    assert updated.artifacts["table"] == "scenarios/tsa24/tsa24-s00.csv"
    assert updated.artifacts["record"] == "scenarios/tsa24/tsa24-s00.result.yaml"

    with table_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert list(rows[0]) == list(TABLE_COLUMNS)
    assert len(rows) == 17  # header + 16 periods
    assert rows[1][0] == "1"

    loaded = load_scenario_result(record_path)
    assert loaded == updated


def test_write_is_deterministic(fixture_model, tmp_path: Path) -> None:
    result = _run(fixture_model)
    first = write_scenario_result(result, tmp_path / "results-a")
    second = write_scenario_result(result, tmp_path / "results-b")
    assert first.artifacts == second.artifacts
    for relative in first.artifacts.values():
        a = (tmp_path / "results-a" / relative).read_bytes()
        b = (tmp_path / "results-b" / relative).read_bytes()
        assert a == b


def test_namespace_override(fixture_model, tmp_path: Path) -> None:
    result = _run(fixture_model)
    updated = write_scenario_result(result, tmp_path / "results", namespace="campaign-a")
    assert updated.artifacts["table"].startswith("scenarios/campaign-a/")
    assert (tmp_path / "results" / updated.artifacts["table"]).is_file()
