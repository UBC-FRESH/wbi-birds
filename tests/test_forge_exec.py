from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("freshforge")

from conftest import FIXTURE_DIR, FIXTURE_MODEL, INSTANCE_FIXTURE

from wbi_birds.mapping import load_ws3_sections, stage_ws3_sections
from wbi_birds.results import load_scenario_result

WORKFLOW = """
workflow:
  id: wbi_smoke
  name: WBI smoke workflow (fixture instance)
nodes:
  - id: build_model
    provider: wbi.build_model
    parameters:
      instance: instances/tsa24
    outputs:
      forest_model: fixture_model
  - id: run_scenarios
    provider: wbi.run_scenarios
    needs: [build_model]
    inputs:
      forest_model: build_model.forest_model
    outputs:
      scenario_results: tsa24_s00
    parameters:
      instance: instances/tsa24
      management_unit: TSA24
      scenario_id: tsa24-s00
      objective_expr: "totvol * 0.85"
      constraint_expr: "totvol"
      even_flow_epsilon: null
"""


def test_freshforge_run_smoke(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    instance = workdir / "instances" / "tsa24"
    instance.parent.mkdir(parents=True)
    shutil.copytree(INSTANCE_FIXTURE, instance)
    stage_ws3_sections(load_ws3_sections(FIXTURE_DIR, FIXTURE_MODEL), instance)

    workflow = tmp_path / "smoke.yaml"
    workflow.write_text(WORKFLOW)
    evidence = tmp_path / "evidence.json"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "freshforge",
            "run",
            str(workflow),
            "--workdir",
            str(workdir),
            "--json",
            "--evidence",
            str(evidence),
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    payload = json.loads(proc.stdout)
    assert payload.get("ok") is True, payload
    assert payload["run"]["status"] == "success"

    table = instance / "results" / "scenarios" / "tsa24" / "tsa24-s00.csv"
    record = instance / "results" / "scenarios" / "tsa24" / "tsa24-s00.result.yaml"
    assert table.is_file()
    assert record.is_file()
    loaded = load_scenario_result(record)
    assert loaded.status == "optimal"
    assert loaded.harvest_volume_total_m3 is not None
    assert loaded.harvest_volume_total_m3 > 0

    assert evidence.is_file()
    evidence_text = evidence.read_text()
    assert "wbi_smoke" in evidence_text
    assert "success" in evidence_text
