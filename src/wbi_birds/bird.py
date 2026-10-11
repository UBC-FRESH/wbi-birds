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

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from ws3.forest import ForestModel

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


def bird_unit_value(
    model: ForestModel,
    dtype_key: tuple[str, ...],
    age: int,
    coefficients: AnticipationCoefficients,
) -> float:
    """Bird abundance per hectare for one development type at one age."""
    development_type = model.dt(dtype_key)
    softwood = development_type.ycomp("swdvol")
    hardwood = development_type.ycomp("hwdvol")
    if softwood is None or hardwood is None:
        raise ValueError(f"Development type {' '.join(dtype_key)} lacks swdvol/hwdvol yield curves")
    return (
        coefficients.swvol * softwood[age]
        + coefficients.hwvol * hardwood[age]
        + coefficients.age * age
        + coefficients.intercept
    )


def compile_bird_coefficients(
    model: ForestModel,
    path: Any,
    *,
    coefficients: AnticipationCoefficients,
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
    coefficients: AnticipationCoefficients,
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
