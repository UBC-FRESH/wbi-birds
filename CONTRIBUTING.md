# Contributing

Thanks for your interest in wbi-birds! This repo follows the UBC FRESH lab workflow.

## Development setup

    python -m venv .venv && . .venv/bin/activate
    pip install -e .[dev]

## Before opening a PR

    ruff format src tests
    ruff check src tests
    pytest
    sphinx-build -b html docs docs/_build/html -W

## Workflow

- Work happens on phase branches (`feature/issue-<N>-<slug>`), one per roadmap phase.
- Commits reference roadmap task IDs (e.g., `E-P3.2`).
- CI must be green; docs warnings are errors.

See `AGENTS.md` and `ROADMAP.md`.
