from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from wbi_birds import __version__
from wbi_birds.cli import app
from wbi_birds.fit import make_covariates_csv
from wbi_birds.responses import ResponseTable, write_response_tables

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_instance_validate_cli() -> None:
    result = runner.invoke(app, ["instance", "validate", str(FIXTURE)])
    assert result.exit_code == 0
    assert "OK" in result.stdout


def test_fit_poisson_cli(tmp_path: Path) -> None:
    covariates = make_covariates_csv(
        [(50.0, 5.0, 40.0), (150.0, 2.0, 90.0), (250.0, 0.0, 140.0)],
        [1.0, 5.0, 9.0],
        tmp_path / "covariates.csv",
    )
    result = runner.invoke(app, ["fit", "poisson", str(covariates)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert "coefficients" in payload
    assert set(payload["coefficients"]) == {"intercept", "swvol", "hwvol", "age"}


def test_fit_stage_response_cli(tmp_path: Path) -> None:
    instance = tmp_path / "instance"
    shutil.copytree(FIXTURE, instance)
    dtype = ("dt", "0", "1", "1", "1")
    source = tmp_path / "source.csv"
    write_response_tables(
        source,
        [ResponseTable(species_code="rebnut", values={(dtype, 80): 12.5})],
    )
    result = runner.invoke(app, ["fit", "stage-response", str(source), str(instance), "rebnut"])
    assert result.exit_code == 0, result.output
    assert "response_table.csv" in result.stdout
