from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytest.importorskip("freshforge")

from conftest import FIXTURE_DIR, INSTANCE_FIXTURE

EBD_FIXTURE = Path(__file__).parent / "fixtures" / "ebd" / "sample_ebd.txt"

WORKFLOW = """
workflow:
  id: wbi_chain_full
  name: WBI full chain (ingest -> fit -> compile -> model -> bird scenario)
nodes:
  - id: ingest_ebd
    provider: wbi.ingest_ebd
    outputs:
      derived_tables: ebd_suite
    parameters:
      instance: instances/tsa24
      ebd: data/sample_ebd.txt
      months: [5, 8]
  - id: fit_antifunction
    provider: wbi.fit_antifunction
    needs: [ingest_ebd]
    inputs:
      derived_tables: ingest_ebd.derived_tables
    outputs:
      coefficients: suite_coefficients
    parameters:
      instance: instances/tsa24
      mode: provided
      coefficients: assets/coefficients.yaml
  - id: compile_instance
    provider: wbi.compile_instance
    needs: [fit_antifunction]
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
      constraint_expr: "bird"
      bird_species: rebnut
      even_flow_epsilon: null
"""


def test_freshforge_full_chain(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    instance = workdir / "instances" / "tsa24"
    instance.parent.mkdir(parents=True)
    shutil.copytree(INSTANCE_FIXTURE, instance)

    (workdir / "data").mkdir()
    shutil.copyfile(EBD_FIXTURE, workdir / "data" / "sample_ebd.txt")

    (workdir / "assets").mkdir()
    coefficients_source = workdir / "assets" / "coefficients.yaml"
    payload = yaml.safe_load((instance / "bird" / "coefficients.yaml").read_text())
    payload["species"]["rebnut"]["intercept"] = 0.5  # provably different from the fixture
    coefficients_source.write_text(yaml.safe_dump(payload, sort_keys=False))

    bundles = workdir / "bundles" / "tsa24"
    bundles.parent.mkdir(parents=True)
    shutil.copytree(FIXTURE_DIR, bundles)

    workflow = tmp_path / "chain_full.yaml"
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
    result = json.loads(proc.stdout)
    assert result.get("ok") is True, result
    assert result["run"]["status"] == "success"

    derived = instance / "bird" / "derived" / "ebd_suite.csv"
    assert derived.is_file()
    assert (instance / "bird" / "derived" / "ebd_suite.csv.provenance.json").is_file()
    assert (instance / "inputs" / "ws3" / "tsa24_clipped.lan").is_file()

    staged = yaml.safe_load((instance / "bird" / "coefficients.yaml").read_text())
    assert staged["species"]["rebnut"]["intercept"] == 0.5
    assert staged["source"]["fit"] == "provided"

    results = instance / "results" / "scenarios" / "tsa24" / "tsa24-s00.csv"
    assert results.is_file()

    run_node = next(node for node in result["run"]["nodes"] if node["id"] == "run_scenarios")
    bird_total = run_node["outputs"]["scenario_results"]["bird_abundance_total"]
    assert bird_total is not None
    assert bird_total > 0
    assert evidence.is_file()
