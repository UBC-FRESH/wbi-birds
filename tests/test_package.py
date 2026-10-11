from typer.testing import CliRunner

from wbi_birds import __version__
from wbi_birds.cli import app


def test_version() -> None:
    assert __version__ == "0.1.0a1"


def test_cli_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
