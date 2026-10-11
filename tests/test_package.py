import tomllib
from pathlib import Path

from typer.testing import CliRunner

from wbi_birds import __version__
from wbi_birds.cli import app

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version() -> None:
    metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert __version__ == metadata["project"]["version"]


def test_cli_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
