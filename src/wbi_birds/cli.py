"""Command-line interface for wbi-birds."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from wbi_birds import __version__
from wbi_birds.fit import fit_covariates, stage_response_table_from_csv
from wbi_birds.instance import ERROR, validate_instance

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="wbi-birds: epsilon-constraint harvest-bird-abundance tradeoff engine (ws3-based).",
)

instance_app = typer.Typer(no_args_is_help=True, help="Instance tools (data contract).")
app.add_typer(instance_app, name="instance")

fit_app = typer.Typer(
    no_args_is_help=True,
    help="Bird response fitting (native Python; no R/SpaDES).",
)
app.add_typer(fit_app, name="fit")


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


@fit_app.command("poisson")
def fit_poisson(
    covariates: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        help="Covariates CSV with columns: observation_count,swvol,hwvol,age.",
    ),
    stepwise: bool = typer.Option(
        False,
        "--stepwise",
        help="Run stepwise AIC selection (MASS::stepAIC equivalent).",
    ),
    direction: str = typer.Option(
        "both",
        help="Stepwise direction: backward | forward | both.",
    ),
) -> None:
    """Fit the native Poisson GLM and print coefficients + fit statistics (JSON)."""
    result = fit_covariates(covariates, stepwise=stepwise, direction=direction)
    typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=float))


@fit_app.command("stage-response")
def fit_stage_response(
    table: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Source response_table.csv (any number of species)."
    ),
    instance: Path = typer.Argument(
        ..., exists=True, file_okay=False, help="Instance root directory."
    ),
    species: str = typer.Argument(..., help="Species code to stage (e.g. rebnut)."),
) -> None:
    """Stage one species' precomputed response table into an instance."""
    path = stage_response_table_from_csv(table, instance, species, fit_note="provided")
    typer.echo(str(path))


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
