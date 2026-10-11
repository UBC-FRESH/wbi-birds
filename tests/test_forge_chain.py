from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytest.importorskip("freshforge")

from conftest import FIXTURE_DIR, FRESH_PROCESS_ENV, INSTANCE_FIXTURE

WORKFLOW = """
workflow:
  id: wbi_chain
  name: WBI chain (femic bundle -> instance -> model -> scenario)
nodes:
  - id: compile_instance
    provider: wbi.compile_instance
    outputs:
      instance_root: tsa24_instance
    parameters:
      instance: instances/tsa24
      femic_bundle: bundles/tsa24
      management_unit: TSA24
  - id: build_model
    provider: wbi.build_model
    needs: [compile_instance]
    parameters:
      instance: instances/tsa24
    outputs:
      forest_model: tsa24_model
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


def test_freshforge_run_chain(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    instance = workdir / "instances" / "tsa24"
    instance.parent.mkdir(parents=True)
    shutil.copytree(INSTANCE_FIXTURE, instance)
    bundles = workdir / "bundles" / "tsa24"
    bundles.parent.mkdir(parents=True)
    shutil.copytree(FIXTURE_DIR, bundles)

    workflow = tmp_path / "chain.yaml"
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
        env=FRESH_PROCESS_ENV,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    payload = json.loads(proc.stdout)
    assert payload.get("ok") is True, payload
    assert payload["run"]["status"] == "success"

    staged = instance / "inputs" / "ws3" / "tsa24_clipped.lan"
    assert staged.is_file()
    run_config = yaml.safe_load((instance / "config" / "run.yaml").read_text())
    assert run_config["management_unit"]["id"] == "TSA24"
    results = instance / "results" / "scenarios" / "tsa24" / "tsa24-s00.csv"
    assert results.is_file()
    assert evidence.is_file()
