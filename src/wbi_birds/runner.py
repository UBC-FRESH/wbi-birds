"""ε-constraint scenario runner (E-P3.2).

Wraps ws3's ``ForestModel.add_problem`` / ``Problem.solve`` to execute the
paper's ε-constraint experiment: maximize even-flow harvest volume subject to
general lower bounds (floors) on a second output row (bird abundance once E-P4
supplies the anticipation-function row; a generic output row until then).

Coefficient functions mirror the legacy ``spades_ws3`` implementation
(``cmp_c_z`` / ``cmp_c_caa`` over ``fm.compile_product``).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

from ws3 import opt as ws3opt
from ws3.forest import ForestModel

from wbi_birds import __version__
from wbi_birds.scenarios import ScenarioResult, SolverResult

VALID_STATUSES = ("optimal", "infeasible", "unbounded")


class ScenarioRunError(ValueError):
    """Raised when a scenario cannot be set up or executed."""


@dataclass(frozen=True)
class ProblemSpec:
    """LP formulation for the WBI ε-constraint experiment."""

    objective_expr: str
    constraint_row: str
    constraint_expr: str
    harvest_acodes: tuple[str, ...] = ("harvest",)
    acodes: tuple[str, ...] = ("null", "harvest")
    even_flow_epsilon: float | None = 0.10
    even_flow_ref_period: int | None = None


def _coeff_z(fm: ForestModel, path: Any, expr: str) -> float:
    """Objective coefficient: total product over harvest actions on a path."""
    result = 0.0
    for t, node in enumerate(path, start=1):
        data = node.data()
        if fm.is_harvest(data["acode"]):
            result += fm.compile_product(
                t, expr, data["acode"], [data["dtk"]], data["age"], coeff=False
            )
    return result


def _coeff_flow(fm: ForestModel, path: Any, expr: str, acodes: tuple[str, ...]) -> dict[int, float]:
    """Flow-constraint coefficients per period for the given action codes."""
    result: dict[int, float] = {}
    for t, node in enumerate(path, start=1):
        data = node.data()
        if data["acode"] in acodes:
            result[t] = fm.compile_product(
                t, expr, data["acode"], [data["dtk"]], data["age"], coeff=False
            )
    return result


def _solver_version(solver: str) -> str:
    try:
        if solver == ws3opt.SOLVER_HIGHS:
            import highspy

            return str(getattr(highspy, "__version__", ""))
        if solver == ws3opt.SOLVER_GUROBI:
            import gurobipy

            return str(getattr(gurobipy, "__version__", ""))
    except ImportError:
        return ""
    return ""


def _prepare_model(fm: ForestModel) -> None:
    fm.initialize_areas()
    fm.reset_actions()


def run_scenario(
    fm: ForestModel,
    spec: ProblemSpec,
    *,
    scenario_id: str,
    management_unit: str,
    constraint_floor: float | Mapping[int, float] | None = None,
    solver: str = ws3opt.SOLVER_HIGHS,
    artifacts: dict[str, str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> ScenarioResult:
    """Run one ε-constraint scenario against a built model.

    ``constraint_floor`` is the per-period lower bound on the constraint row —
    a scalar (uniform) or a period-keyed mapping (None = unconstrained/nadir).
    Even-flow (if enabled) bounds the objective row within
    ±``even_flow_epsilon`` of the reference period.
    """
    for acode in spec.acodes:
        if acode not in fm.actions:
            raise ScenarioRunError(f"Action '{acode}' is not defined in the model")

    _prepare_model(fm)

    coeff_funcs: dict[str, Callable[..., Any]] = {
        "z": partial(_coeff_z, expr=spec.objective_expr),
        f"row_{spec.constraint_row}": partial(
            _coeff_flow, expr=spec.constraint_expr, acodes=spec.harvest_acodes
        ),
    }
    cflw_e: dict[str, Any] | None = None
    if spec.even_flow_epsilon is not None:
        ref_period = (
            spec.even_flow_ref_period if spec.even_flow_ref_period is not None else fm.periods[-1]
        )
        coeff_funcs["cflw"] = partial(
            _coeff_flow, expr=spec.objective_expr, acodes=spec.harvest_acodes
        )
        cflw_e = {"cflw": (dict.fromkeys(fm.periods, spec.even_flow_epsilon), ref_period)}

    cgen_data: dict[str, Any] | None = None
    floor_provenance: dict[str, float] | float | None = None
    if constraint_floor is not None:
        if isinstance(constraint_floor, Mapping):
            floors = {int(t): float(v) for t, v in constraint_floor.items()}
            floor_provenance = {str(t): v for t, v in floors.items()}
        else:
            floors = dict.fromkeys(fm.periods, float(constraint_floor))
            floor_provenance = float(constraint_floor)
        cgen_data = {f"row_{spec.constraint_row}": {"lb": floors}}

    started = time.monotonic()
    problem = fm.add_problem(
        name=scenario_id,
        coeff_funcs=coeff_funcs,
        cflw_e=cflw_e,
        cgen_data=cgen_data,
        solver=solver,
        formulation=1,
        sense=ws3opt.SENSE_MAXIMIZE,
        acodes=list(spec.acodes),
    )
    problem.solve()
    runtime_seconds = time.monotonic() - started

    raw_status = problem.status() or "error"
    status = raw_status if raw_status in VALID_STATUSES else "error"
    harvest_series: list[float] = []
    constraint_series: list[float] = []
    objective_value: float | None = None
    if status == "optimal":
        objective_value = problem.z()
        schedule = fm.compile_schedule(problem)
        fm.reset()
        fm.apply_schedule(
            schedule,
            force_integral_area=False,
            override_operability=False,
            fuzzy_age=False,
            recourse_enabled=False,
            verbose=False,
            compile_c_ycomps=True,
        )
        harvest_series = [
            float(fm.compile_product(t, spec.objective_expr, acode="harvest")) for t in fm.periods
        ]
        constraint_series = [
            float(fm.compile_product(t, spec.constraint_expr, acode="harvest")) for t in fm.periods
        ]

    diagnostics = [f"ws3 solver status: {raw_status}"]
    result_provenance = {
        "objective_expr": spec.objective_expr,
        "constraint_expr": spec.constraint_expr,
        "even_flow_epsilon": spec.even_flow_epsilon,
        "constraint_floor": floor_provenance,
    }
    if objective_value is not None:
        result_provenance["objective_value"] = objective_value
    if provenance:
        result_provenance.update(provenance)

    return ScenarioResult(
        scenario_id=scenario_id,
        management_unit=management_unit,
        status=status,  # type: ignore[arg-type]
        harvest_volume_m3_by_period=harvest_series,
        bird_abundance_by_period=constraint_series,
        harvest_volume_total_m3=sum(harvest_series) if harvest_series else None,
        bird_abundance_total=sum(constraint_series) if constraint_series else None,
        solver=SolverResult(
            backend=solver,  # type: ignore[arg-type]
            backend_version=_solver_version(solver),
            status_raw=raw_status,
            runtime_seconds=runtime_seconds,
        ),
        artifacts=artifacts or {},
        diagnostics=diagnostics,
        engine_version=__version__,
        provenance=result_provenance,
    )
