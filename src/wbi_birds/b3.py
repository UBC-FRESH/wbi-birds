"""B3 comparison: habitat-only reserves vs integrated ε-constraints (E-P3.5).

Sequential arm: reserves are excluded from harvest, then harvest is maximized
(the "planned outside the model" conservation strategy). Integrated arm: the
ε-constraint grid on the same model. Outcomes are matched at equal bird
abundance by linear interpolation on the integrated frontier.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ws3.forest import ForestModel

from wbi_birds.reserves import ReserveSelection, apply_reserve_exclusion
from wbi_birds.runner import ProblemSpec, run_scenario
from wbi_birds.scenarios import ScenarioResult


@dataclass(frozen=True)
class B3Result:
    """Outcome of the B3 sequential-vs-integrated comparison."""

    management_unit: str
    reserve: dict[str, Any]
    sequential: dict[str, Any]
    integrated_frontier: tuple[dict[str, Any], ...]
    matched: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _summarize(result: ScenarioResult) -> dict[str, Any]:
    return {
        "scenario_id": result.scenario_id,
        "status": result.status,
        "harvest_volume_total_m3": result.harvest_volume_total_m3,
        "bird_abundance_total": result.bird_abundance_total,
        "solver": result.solver.model_dump(mode="json"),
    }


def interpolate_harvest(frontier: Sequence[dict[str, Any]], bird_target: float) -> float | None:
    """Linear interpolation of integrated harvest totals at a bird-abundance target."""
    points = sorted(
        (
            point
            for point in frontier
            if point["status"] == "optimal"
            and point["bird_abundance_total"] is not None
            and point["harvest_volume_total_m3"] is not None
        ),
        key=lambda point: point["bird_abundance_total"],
    )
    for low, high in itertools.pairwise(points):
        bird_low = low["bird_abundance_total"]
        bird_high = high["bird_abundance_total"]
        if bird_low <= bird_target <= bird_high and bird_high > bird_low:
            harvest_low = low["harvest_volume_total_m3"]
            harvest_high = high["harvest_volume_total_m3"]
            t = (bird_target - bird_low) / (bird_high - bird_low)
            return harvest_low + t * (harvest_high - harvest_low)
    return None


def run_b3_comparison(
    integrated_model: ForestModel,
    sequential_model: ForestModel,
    spec: ProblemSpec,
    selection: ReserveSelection,
    *,
    management_unit: str,
    floors: Sequence[float | Mapping[int, float] | None] = (None,),
    solver: str = "highs",
) -> B3Result:
    """Run both arms and match outcomes at equal bird abundance."""
    apply_reserve_exclusion(sequential_model, selection)
    sequential = run_scenario(
        sequential_model,
        spec,
        scenario_id=f"{management_unit.lower()}-seq-reserve",
        management_unit=management_unit,
        solver=solver,
    )

    frontier: list[dict[str, Any]] = []
    for index, floor in enumerate(floors):
        result = run_scenario(
            integrated_model,
            spec,
            scenario_id=f"{management_unit.lower()}-int-{index:02d}",
            management_unit=management_unit,
            constraint_floor=floor,
            solver=solver,
        )
        entry = _summarize(result)
        if floor is None:
            entry["constraint_floor"] = None
        elif isinstance(floor, Mapping):
            entry["constraint_floor"] = {str(k): v for k, v in floor.items()}
        else:
            entry["constraint_floor"] = float(floor)
        frontier.append(entry)

    matched: dict[str, Any] = {
        "bird_target": sequential.bird_abundance_total,
        "harvest_sequential_m3": sequential.harvest_volume_total_m3,
    }
    harvest_integrated: float | None = None
    if sequential.bird_abundance_total is not None:
        harvest_integrated = interpolate_harvest(frontier, sequential.bird_abundance_total)
    matched["harvest_integrated_m3"] = harvest_integrated
    if harvest_integrated is not None and sequential.harvest_volume_total_m3 is not None:
        matched["reserve_penalty_m3"] = sequential.harvest_volume_total_m3 - harvest_integrated
    elif sequential.bird_abundance_total is not None:
        matched["note"] = (
            "bird target outside the integrated frontier range (harvest-row measurement "
            "scope; revisit with the E-P4 landscape bird row)"
        )

    return B3Result(
        management_unit=management_unit,
        reserve=selection.to_dict(),
        sequential=_summarize(sequential),
        integrated_frontier=tuple(frontier),
        matched=matched,
    )


def write_b3_result(result: B3Result, results_root: Path | str) -> Path:
    """Write the B3 comparison record (deterministic JSON)."""
    root = Path(results_root)
    target = root / "b3"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{result.management_unit.lower()}-reserve-comparison.json"
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
