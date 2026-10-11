"""Command-line interface for wbi-birds."""

import typer

from wbi_birds import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="wbi-birds: epsilon-constraint harvest-bird-abundance tradeoff engine (ws3-based).",
)


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
