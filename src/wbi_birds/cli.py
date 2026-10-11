"""Command-line interface for wbi-birds."""

from pathlib import Path

import typer

from wbi_birds import __version__
from wbi_birds.instance import ERROR, validate_instance

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="wbi-birds: epsilon-constraint harvest-bird-abundance tradeoff engine (ws3-based).",
)

instance_app = typer.Typer(no_args_is_help=True, help="Instance tools (data contract).")
app.add_typer(instance_app, name="instance")


@instance_app.command("validate")
def instance_validate(
    path: Path = typer.Argument(..., exists=True, file_okay=False, help="Instance root directory."),
) -> None:
    """Validate an instance directory against the data contract."""
    issues = validate_instance(path)
    for issue in issues:
        typer.echo(f"{issue.severity}: {issue.code}: {issue.message} [{issue.path}]")
    errors = [issue for issue in issues if issue.severity == ERROR]
    if errors:
        typer.echo(f"{len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
        raise typer.Exit(code=1)
    typer.echo(f"OK ({len(issues)} warning(s))")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """WBI birds simulation engine."""
