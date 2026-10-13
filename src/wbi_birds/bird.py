"""Bird anticipation row (E-P4.1).

The paper's anticipation function, evaluated directly from each development
type's resolved volume curves:

    bird(age) = c1 * softwood_volume(age) + c2 * hardwood_volume(age)
                + c3 * age + c4

The engine owns this row: it is compiled into LP constraint-row coefficients
(area-weighted, same semantics as ws3 product rows) and into post-hoc series.
This avoids ws3's complex-yield resolver (which cannot nest resolver calls) and
works for runtime-created development types. Coefficient names follow the
legacy WBI convention (``birdaf_*_coeff``).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from ws3.forest import ForestModel

from wbi_birds import __version__
from wbi_birds.responses import (
    RESPONSE_TABLE_RELPATH,
    ResponseTable,
    ResponseTableError,
    dtype_key_to_str,
    read_response_tables,
)

BIRD_ROW = "bird"


@dataclass(frozen=True)
class AnticipationCoefficients:
    """Fitted coefficients of the bird abundance anticipation function."""

    swvol: float
    hwvol: float
    age: float
    intercept: float

    @classmethod
    def from_mapping(cls, data: dict[str, float]) -> AnticipationCoefficients:
        return cls(
            swvol=float(data["swvol"]),
            hwvol=float(data["hwvol"]),
            age=float(data["age"]),
            intercept=float(data["intercept"]),
        )

    def to_constants(self) -> dict[str, float]:
        """Provenance-style constants (legacy WBI naming)."""
        return {
            "birdaf_swvol_coeff": self.swvol,
            "birdaf_hwvol_coeff": self.hwvol,
            "birdaf_age_coeff": self.age,
            "birdaf_intercept_coeff": self.intercept,
        }


BirdResponse = AnticipationCoefficients | ResponseTable


def load_coefficients(instance_root: Path | str, species_code: str) -> AnticipationCoefficients:
    """Load a species' coefficients from the instance's ``bird/coefficients.yaml``."""
    path = Path(instance_root) / "bird" / "coefficients.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Coefficients file is not a mapping: {path}")
    entry = (data.get("species") or {}).get(species_code)
    if not isinstance(entry, dict):
        raise ValueError(f"No coefficients for species '{species_code}' in {path}")
    return AnticipationCoefficients.from_mapping(entry)


def load_bird_response(instance_root: Path | str, species_code: str) -> BirdResponse:
    """Load a species' response: response table if present, else coefficients.

    The response table takes precedence so a v2 ensemble can be staged without
    removing the legacy coefficients (which remain available for parity).
    """
    path = Path(instance_root) / RESPONSE_TABLE_RELPATH
    if path.is_file():
        tables = read_response_tables(path)
        if species_code in tables:
            return tables[species_code]
    return load_coefficients(instance_root, species_code)


def bird_unit_value(
    model: ForestModel,
    dtype_key: tuple[str, ...],
    age: int,
    response: BirdResponse,
) -> float:
    """Bird abundance per hectare for one development type at one age.

    ``response`` may be the legacy linear :class:`AnticipationCoefficients` or a
    precomputed :class:`ResponseTable` produced by evaluating any fitted model on
    the planning state space. The LP stays linear in the prescription variables
    because this value is compiled as a fixed row coefficient.
    """
    if isinstance(response, ResponseTable):
        return response.unit_value(dtype_key, age)
    development_type = model.dt(dtype_key)
    softwood = development_type.ycomp("swdvol")
    hardwood = development_type.ycomp("hwdvol")
    if softwood is None or hardwood is None:
        raise ValueError(f"Development type {' '.join(dtype_key)} lacks swdvol/hwdvol yield curves")
    return (
        response.swvol * softwood[age]
        + response.hwvol * hardwood[age]
        + response.age * age
        + response.intercept
    )


def compile_bird_coefficients(
    model: ForestModel,
    path: Any,
    *,
    coefficients: BirdResponse,
    acodes: Sequence[str],
) -> dict[int, float]:
    """LP constraint-row coefficients for the bird row along one prescription path."""
    result: dict[int, float] = {}
    for period, node in enumerate(path, start=1):
        data = node.data()
        if data["acode"] not in acodes:
            continue
        area = model.compile_product(
            period, "1.", data["acode"], [data["dtk"]], data["age"], coeff=False
        )
        result[period] = area * bird_unit_value(model, data["dtk"], data["age"], coefficients)
    return result


def compile_bird_row(
    model: ForestModel,
    coefficients: BirdResponse,
    *,
    acodes: Sequence[str],
) -> list[float]:
    """Per-period bird abundance for the currently applied schedule, by action scope."""
    series: list[float] = []
    for period in model.periods:
        total = 0.0
        actions = model.applied_actions.get(period, {})
        for acode in acodes:
            for dtype_key, ages in actions.get(acode, {}).items():
                for age, slot in ages.items():
                    area = slot[0]
                    if area > 0:
                        total += area * bird_unit_value(model, dtype_key, int(age), coefficients)
        series.append(total)
    return series


def _prepare_for_state_space(model: ForestModel) -> None:
    """Reset areas/actions before a dry prescription-graph pass (mirrors the runner)."""
    model.initialize_areas()
    model.reset_actions()


def state_space(
    model: ForestModel,
    *,
    ages: Sequence[int] | None = None,
) -> list[tuple[tuple[str, ...], int]]:
    """All ``(development type, age)`` pairs currently registered on the model.

    Enumerates development types as they exist now. Transition (regeneration)
    types are created during prescription-graph compilation, so prefer
    :func:`reachable_state_space` when building response tables for a full
    scenario run. Pass ``ages`` to restrict (e.g. the operability window) and
    keep response tables small. Raises if a requested age is outside a
    development type's curves.
    """
    pairs: list[tuple[tuple[str, ...], int]] = []
    for dtype_key in model.dtypes:
        development_type = model.dt(dtype_key)
        softwood = development_type.ycomp("swdvol")
        hardwood = development_type.ycomp("hwdvol")
        if softwood is None or hardwood is None:
            continue
        available = {int(year) for year in softwood.x}
        requested = [int(age) for age in (ages if ages is not None else available)]
        for age in requested:
            if age not in available:
                raise ValueError(
                    f"Age {age} is not in the yield curves for development type "
                    f"'{dtype_key_to_str(dtype_key)}'."
                )
            pairs.append((tuple(dtype_key), age))
    return pairs


def reachable_state_space(
    model: ForestModel,
    *,
    acodes: Sequence[str] = ("null", "harvest"),
    ages: Sequence[int] | None = None,
) -> list[tuple[tuple[str, ...], int]]:
    """Enumerate every ``(development type, age)`` the prescription graph reaches.

    Transition/regeneration development types are created while prescription
    graphs are compiled, so a throwaway (unsolved) ``add_problem`` pass is used
    to materialise them before enumeration. The problem is discarded; the newly
    created development types remain on the model. Call this **once** and reuse
    the result for all species when building response tables.
    """
    seen: set[tuple[tuple[str, ...], int]] = set()

    def probe(fm: ForestModel, path: Any) -> float:
        for node in path:
            data = node.data()
            seen.add((tuple(data["dtk"]), int(data["age"])))
        return 0.0

    _prepare_for_state_space(model)
    model.add_problem(
        name="__wbi_bird_state_space__",
        coeff_funcs={"probe": probe, "z": lambda fm, path: 0.0},
        acodes=list(acodes),
    )
    if ages is not None:
        allowed = {int(age) for age in ages}
        seen = {pair for pair in seen if pair[1] in allowed}
    return sorted(seen)


def build_response_table(
    model: ForestModel,
    species_code: str,
    predict: Callable[[float, float, int], float],
    *,
    states: Sequence[tuple[tuple[str, ...], int]] | None = None,
    acodes: Sequence[str] | None = None,
    ages: Sequence[int] | None = None,
    sd: Callable[[float, float, int], float] | None = None,
    source: Mapping[str, Any] | None = None,
) -> ResponseTable:
    """Evaluate a fitted predictor onto the reachable planning state space.

    ``predict(softwood, hardwood, age)`` returns the fitted (ensemble) response
    in the same units as the LP bird row (per hectare). The predictor may be
    arbitrarily non-linear; it is reproduced exactly because the row is a fixed
    coefficient per ``(development type, age)``. Pass a precomputed ``states``
    (from :func:`reachable_state_space`) when building tables for several
    species to avoid repeating the dry enumeration pass. Without ``states``, pass the
    configured harvest actions as ``acodes`` (``model.harvest_acodes``); the null action is
    always included. Non-finite predicted values are rejected.
    """
    if states is None:
        if acodes is None:
            raise ValueError(
                "build_response_table needs states or acodes: pass the configured harvest "
                "actions (model.harvest_acodes) so the table covers the campaign's states."
            )
        states = reachable_state_space(
            model, acodes=tuple(dict.fromkeys(("null", *acodes))), ages=ages
        )
    values: dict[tuple[tuple[str, ...], int], float] = {}
    sd_values: dict[tuple[tuple[str, ...], int], float] = {}
    for dtype_key, age in states:
        development_type = model.dt(dtype_key)
        softwood = development_type.ycomp("swdvol")
        hardwood = development_type.ycomp("hwdvol")
        assert softwood is not None and hardwood is not None
        value = float(predict(softwood[age], hardwood[age], age))
        if not math.isfinite(value):
            raise ResponseTableError(f"Non-finite predicted value for {dtype_key} age {age}.")
        values[(dtype_key, age)] = value
        if sd is not None:
            spread = float(sd(softwood[age], hardwood[age], age))
            if not math.isfinite(spread):
                raise ResponseTableError(f"Non-finite predicted spread for {dtype_key} age {age}.")
            sd_values[(dtype_key, age)] = spread
    return ResponseTable(
        species_code=species_code,
        values=values,
        sd=sd_values,
        source={"engine_version": __version__, **dict(source or {})},
    )
