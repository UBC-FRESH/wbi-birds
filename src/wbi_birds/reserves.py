"""B3 reserve-network support (E-P3.5).

Sequential-conservation arm of the B3 experiment (`UBC-FRESH/wbi-birds-manuscript#14`):
a habitat-only reserve network — selected without any harvesting economics — is
made harvest-inoperable and compared against the integrated ε-constraint
results at matched bird-abundance targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ws3.forest import ForestModel

IMPOSSIBLE_EXPR = "_age >= 99999"  # supported operator; unreachable age bound


@dataclass(frozen=True)
class ReserveSelection:
    """A habitat-only reserve network selection."""

    criterion: str
    dtype_keys: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "dtype_count": len(self.dtype_keys),
            "dtype_keys": [list(key) for key in self.dtype_keys],
        }


def select_reserves_by_min_age(model: ForestModel, min_age: int) -> ReserveSelection:
    """Habitat-only criterion: stands with initial age ≥ ``min_age`` become reserves.

    Uses only initial inventory ages — no harvesting knowledge.
    """
    keys = tuple(
        sorted(
            key
            for key, development_type in model.dtypes.items()
            if any(age >= min_age and development_type.area(0, age) > 0 for age in model.ages)
        )
    )
    return ReserveSelection(criterion=f"initial_age>={min_age}", dtype_keys=keys)


def apply_reserve_exclusion(
    model: ForestModel,
    selection: ReserveSelection,
    acode: str = "harvest",
) -> None:
    """Make the reserve areas harvest-inoperable (reserves may still stay null/untreated)."""
    for key in selection.dtype_keys:
        development_type = model.dtypes.get(key)
        if development_type is None:
            continue
        if acode in development_type.oper_expr:
            development_type.oper_expr[acode] = [IMPOSSIBLE_EXPR]
