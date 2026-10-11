"""ws3 model building from the instance contract (E-P3.1).

Builds a ``ws3.forest.ForestModel`` from an instance's ``inputs/ws3/`` Woodstock
section bundle (as produced by femic's ws3 bridge) plus the instance run config
(``config/run.yaml``). No femic imports — file contract only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml
from ws3.forest import ForestModel

from wbi_birds.mapping import load_ws3_sections, locate_ws3_bundle

DEFAULT_BASE_YEAR = 2020
DEFAULT_PERIOD_LENGTH_YEARS = 5
DEFAULT_MAX_AGE = 1000
DEFAULT_HARVEST_ACODES: tuple[str, ...] = ("harvest",)


class ModelBuildError(ValueError):
    """Raised when an instance cannot be compiled into a ws3 model."""


@dataclass(frozen=True)
class ModelStats:
    """Provenance-relevant statistics of a built ws3 model."""

    model_name: str
    model_path: str
    base_year: int
    horizon_periods: int
    period_length_years: int
    max_age: int
    dtype_count: int
    action_count: int
    transition_count: int
    curve_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _model_settings(instance_root: Path) -> dict[str, Any]:
    run_path = instance_root / "config" / "run.yaml"
    try:
        run = yaml.safe_load(run_path.read_text())
    except FileNotFoundError as exc:
        raise ModelBuildError(f"Run config not found: {run_path}") from exc
    if not isinstance(run, dict):
        raise ModelBuildError(f"Run config is not a mapping: {run_path}")
    block = run.get("model") or {}
    if not isinstance(block, dict):
        raise ModelBuildError("run.yaml 'model' block must be a mapping")
    try:
        horizon_years = int(run["horizon_years"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelBuildError("run.yaml must define an integer horizon_years") from exc
    period_length_years = int(block.get("period_length_years", DEFAULT_PERIOD_LENGTH_YEARS))
    if period_length_years <= 0 or horizon_years % period_length_years != 0:
        raise ModelBuildError(
            f"horizon_years ({horizon_years}) must be a positive multiple of "
            f"period_length_years ({period_length_years})"
        )
    return {
        "base_year": int(block.get("base_year", DEFAULT_BASE_YEAR)),
        "period_length_years": period_length_years,
        "max_age": int(block.get("max_age", DEFAULT_MAX_AGE)),
        "horizon_periods": horizon_years // period_length_years,
        "harvest_acodes": tuple(
            str(code).lower() for code in block.get("harvest_acodes", DEFAULT_HARVEST_ACODES)
        ),
    }


def build_model(instance_root: Path | str) -> tuple[ForestModel, ModelStats]:
    """Build a ws3 ``ForestModel`` from an instance's ``inputs/ws3/`` bundle.

    Returns the model plus :class:`ModelStats` for provenance recording.
    """
    root = Path(instance_root)
    bundle_dir = root / "inputs" / "ws3"
    model_name = locate_ws3_bundle(bundle_dir)
    sections = load_ws3_sections(bundle_dir, model_name)
    settings = _model_settings(root)
    model = ForestModel(
        model_name=sections.model_name,
        model_path=str(sections.directory),
        base_year=settings["base_year"],
        horizon=settings["horizon_periods"],
        period_length=settings["period_length_years"],
        max_age=settings["max_age"],
    )
    period_years = settings["period_length_years"]
    model.import_landscape_section()
    model.import_areas_section(convert_periods_to_years=period_years)
    model.import_yields_section(convert_periods_to_years=period_years)
    model.import_actions_section(convert_periods_to_years=period_years)
    model.import_transitions_section(convert_periods_to_years=period_years)
    if "null" not in model.actions:
        model.add_null_action()
    for acode in settings["harvest_acodes"]:
        action = model.actions.get(acode)
        if action is None:
            raise ModelBuildError(
                f"Configured harvest action '{acode}' is not defined in the model"
            )
        # The ws3 Woodstock importer currently does not set the harvest flag from the
        # '*ACTION <code> Y' token (UBC-FRESH/ws3#156), so the instance config owns
        # harvest-action semantics explicitly.
        action.is_harvest = 1
    model.reset()
    stats = ModelStats(
        model_name=model.model_name,
        model_path=str(model.model_path),
        base_year=model.base_year,
        horizon_periods=int(model.horizon),
        period_length_years=int(model.period_length),
        max_age=int(model.max_age),
        dtype_count=len(model.dtypes),
        action_count=len(model.actions),
        transition_count=len(model.transitions),
        curve_count=len(model.curves),
    )
    return model, stats
