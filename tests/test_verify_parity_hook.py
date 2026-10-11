from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("freshforge")

from conftest import FIXTURE_DIR, FIXTURE_MODEL, INSTANCE_FIXTURE

from wbi_birds.mapping import load_ws3_sections, stage_ws3_sections
from wbi_birds.model import build_model
from wbi_birds.parity import long_from_engine
from wbi_birds.results import write_scenario_result
from wbi_birds.runner import ProblemSpec, run_scenario

WORKFLOW = """
workflow:
  id: wbi_parity
  name: WBI parity check (single node)
nodes:
  - id: verify_parity
    provider: wbi.verify_parity
    outputs:
      parity_report: suite
    parameters:
      instance: instances/tsa24
      reference: references/suite.csv
      label: tsa24-suite
"""


def _prepare(base: Path, scale: float, strict: bool = False) -> tuple[Path, Path]:
    workdir = base / "workdir"
    instance = workdir / "instances" / "tsa24"
    instance.parent.mkdir(parents=True)
    shutil.copytree(INSTANCE_FIXTURE, instance)
    bundle = load_ws3_sections(FIXTURE_DIR, FIXTURE_MODEL)
    stage_ws3_sections(bundle, instance)

    model, _stats = build_model(instance)
    spec = ProblemSpec(
        objective_expr="totvol * 0.85",
        constraint_row="c",
        constraint_expr="totvol",
        even_flow_epsilon=None,
    )
    result = run_scenario(model, spec, scenario_id="tsa24-s00", management_unit="TSA24")
    assert result.status == "optimal", result.diagnostics
    write_scenario_result(result, instance / "results")

    engine_csv = instance / "results" / "scenarios" / "tsa24" / "tsa24-s00.csv"
    (workdir / "references").mkdir()
    reference = workdir / "references" / "suite.csv"
    rows = long_from_engine(engine_csv, management_unit="TSA24", scenario_id="tsa24-s00")
    with reference.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("management_unit", "scenario_id", "metric", "period", "value"))
        for management_unit, scenario_id, metric, period, value in rows:
            writer.writerow((management_unit, scenario_id, metric, period, value * scale))

    workflow = base / "parity.yaml"
    strict_line = "true" if strict else "false"
    workflow.write_text(
        WORKFLOW.replace("label: tsa24-suite", f"label: tsa24-suite\n      strict: {strict_line}")
    )
    return workdir, workflow


def _run(workdir: Path, workflow: Path, base: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
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
            str(base / "evidence.json"),
        ],
        capture_output=True,
        text=True,
        cwd=str(base),
    )


def test_verify_parity_hook_within_tolerance(tmp_path: Path) -> None:
    base = tmp_path / "within"
    workdir, workflow = _prepare(base, scale=1.0005)
    proc = _run(workdir, workflow, base)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    summary = next(node for node in payload["run"]["nodes"] if node["id"] == "verify_parity")[
        "outputs"
    ]["parity_report"]
    assert summary["n_failed"] == 0
    assert summary["n_compared"] > 0

    parity_dir = workdir / "instances" / "tsa24" / "results" / "parity"
    assert (parity_dir / "tsa24-suite-parity.json").is_file()
    assert (parity_dir / "tsa24-suite-parity.md").is_file()
    evidence_text = (base / "evidence.json").read_text(encoding="utf-8")
    assert "parity_report" in evidence_text
    assert "tsa24-suite" in evidence_text


def test_verify_parity_warns_when_mismatched_and_strict_fails(tmp_path: Path) -> None:
    base = tmp_path / "mismatch"
    workdir, workflow = _prepare(base, scale=1.5)
    proc = _run(workdir, workflow, base)
    payload = json.loads(proc.stdout)
    assert payload.get("ok") is True  # non-strict: warnings only
    summary = next(node for node in payload["run"]["nodes"] if node["id"] == "verify_parity")[
        "outputs"
    ]["parity_report"]
    assert summary["n_failed"] > 0
    node = next(node for node in payload["run"]["nodes"] if node["id"] == "verify_parity")
    warn_codes = {diagnostic["code"] for diagnostic in node["diagnostics"]}
    assert "parity.failed" in warn_codes

    base_strict = tmp_path / "strict"
    workdir_strict, workflow_strict = _prepare(base_strict, scale=1.5, strict=True)
    proc_strict = _run(workdir_strict, workflow_strict, base_strict)
    payload_strict = json.loads(proc_strict.stdout)
    assert payload_strict.get("ok") is False
    error_codes = {diagnostic["code"] for diagnostic in payload_strict["run"]["diagnostics"]} | {
        diagnostic["code"]
        for node in payload_strict["run"]["nodes"]
        for diagnostic in node.get("diagnostics", [])
    }
    assert "parity.strict" in error_codes
