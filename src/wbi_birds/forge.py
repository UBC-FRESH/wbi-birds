"""FreshForge provider for the WBI birds engine.

Plan-only (metadata + validation) for now; execution hooks (``run_node``) arrive
with planning phases E-P3 to E-P5. Registered via the ``freshforge.providers`` entry point
as provider ID ``wbi``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from freshforge.providers import NodeTypeMetadata, ProviderMetadata
from freshforge.records import (
    Diagnostic,
    DiagnosticSeverity,
    ProviderRunResult,
    RunStatus,
    WorkflowNode,
)
from ws3 import opt as ws3opt

from wbi_birds.model import build_model
from wbi_birds.results import write_scenario_result
from wbi_birds.runner import ProblemSpec, run_scenario

PROVIDER_ID = "wbi"
PROVIDER_VERSION = "0.1.0a1"

NODE_TYPES: tuple[NodeTypeMetadata, ...] = (
    NodeTypeMetadata(
        id="ingest_ebd",
        name="Ingest eBird data",
        description=(
            "Filter the private EBD/SED extract to the species suite and derive point-level tables."
        ),
        outputs=("derived_tables",),
        parameters=("species_suite", "months"),
        artifacts=("report",),
    ),
    NodeTypeMetadata(
        id="fit_antifunction",
        name="Fit anticipation functions",
        description=(
            "Fit per-species GLMs (counts ~ softwood/hardwood biomass + age) "
            "and export coefficients."
        ),
        inputs=("derived_tables",),
        outputs=("coefficients",),
        parameters=("family",),
        artifacts=("coefficients",),
    ),
    NodeTypeMetadata(
        id="compile_instance",
        name="Compile instance",
        description=(
            "Compile a per-management-unit instance from femic outputs + "
            "coefficients (data-contract layout)."
        ),
        inputs=("coefficients",),
        outputs=("instance_root",),
        parameters=("femic_bundle", "management_unit"),
        artifacts=("instance",),
    ),
    NodeTypeMetadata(
        id="build_model",
        name="Build ws3 model",
        description="Build the ws3 forest-estate model (Model I, even-flow) for the instance.",
        outputs=("forest_model",),
        parameters=("instance",),
    ),
    NodeTypeMetadata(
        id="run_scenarios",
        name="Run scenario grid",
        description=("Run the ε-constraint scenario grid and write scenario result tables."),
        inputs=("forest_model",),
        outputs=("scenario_results",),
        parameters=(
            "instance",
            "management_unit",
            "scenario_id",
            "objective_expr",
            "constraint_expr",
            "constraint_row",
            "even_flow_epsilon",
            "constraint_floor",
            "solver",
        ),
        artifacts=("results",),
    ),
    NodeTypeMetadata(
        id="compute_frontiers",
        name="Compute frontiers",
        description=(
            "Compute Pareto frontier + marginal opportunity-cost metrics from scenario results."
        ),
        inputs=("scenario_results",),
        outputs=("frontiers",),
    ),
    NodeTypeMetadata(
        id="verify_parity",
        name="Verify legacy parity",
        description=(
            "Compare engine results against legacy RBNU/5-TSA outputs within recorded tolerances."
        ),
        inputs=("scenario_results",),
        outputs=("parity_report",),
        artifacts=("report",),
    ),
    NodeTypeMetadata(
        id="analyze_frontiers",
        name="Analyze + render",
        description="Produce analysis tables, figures, and the claims map for the manuscript.",
        inputs=("frontiers",),
        outputs=("analysis",),
        artifacts=("figures", "claims_map"),
    ),
)


class WbiProvider:
    """Plan-only FreshForge provider for the WBI birds engine."""

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id=PROVIDER_ID,
            version=PROVIDER_VERSION,
            name="WBI birds engine",
            description=(
                "Pipeline nodes for the WBI birds manuscript "
                "(eBird -> regression -> model -> ws3 -> scenarios -> frontiers -> analysis)."
            ),
            node_types=NODE_TYPES,
        )

    def validate_node(
        self,
        node: WorkflowNode,
        node_type: NodeTypeMetadata,
        *,
        location: str,
    ) -> Sequence[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for field_name, declared, actual in (
            ("inputs", node_type.inputs, node.inputs),
            ("outputs", node_type.outputs, node.outputs),
        ):
            for key in declared:
                if key not in actual:
                    diagnostics.append(
                        Diagnostic(
                            severity=DiagnosticSeverity.ERROR,
                            code=f"node.{field_name}.missing",
                            message=(
                                f"Node is missing required provider-declared {field_name} "
                                f"key '{key}'."
                            ),
                            location=f"{location}.{field_name}.{key}",
                        )
                    )
        return diagnostics

    def run_node(
        self,
        node: WorkflowNode,
        node_type: NodeTypeMetadata,
        *,
        context: Any,
    ) -> ProviderRunResult:
        """Execute a WBI node (``build_model`` / ``run_scenarios``)."""
        params = dict(node.parameters or {})
        try:
            if node_type.id == "build_model":
                return self._run_build_model(node, params, context)
            if node_type.id == "run_scenarios":
                return self._run_scenarios(node, params, context)
        except Exception as exc:
            return ProviderRunResult(
                status=RunStatus.FAILED,
                diagnostics=(
                    Diagnostic(
                        severity=DiagnosticSeverity.ERROR,
                        code="node.execution.error",
                        message=f"{type(exc).__name__}: {exc}",
                        location=node.id,
                    ),
                ),
            )
        return ProviderRunResult(
            status=RunStatus.FAILED,
            diagnostics=(
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="node.execution.unsupported",
                    message=f"No execution hook for node type '{node_type.id}'.",
                    location=node.id,
                ),
            ),
        )

    @staticmethod
    def _resolve_instance(params: dict[str, Any], context: Any) -> Path:
        if "instance" not in params:
            raise ValueError("Node parameters must provide 'instance' (path to the instance root)")
        return Path(context.resolve_path(str(params["instance"])))

    def _run_build_model(
        self, node: WorkflowNode, params: dict[str, Any], context: Any
    ) -> ProviderRunResult:
        instance = self._resolve_instance(params, context)
        _model, stats = build_model(instance)
        return ProviderRunResult(
            status=RunStatus.SUCCESS,
            outputs={"forest_model": stats.to_dict()},
            data={"instance": str(instance)},
        )

    def _run_scenarios(
        self, node: WorkflowNode, params: dict[str, Any], context: Any
    ) -> ProviderRunResult:
        instance = self._resolve_instance(params, context)
        for required in ("scenario_id", "objective_expr", "constraint_expr"):
            if required not in params:
                raise ValueError(f"Node parameters must provide '{required}'")
        spec = ProblemSpec(
            objective_expr=str(params["objective_expr"]),
            constraint_row=str(params.get("constraint_row", "constraint")),
            constraint_expr=str(params["constraint_expr"]),
            even_flow_epsilon=params.get("even_flow_epsilon", 0.10),
        )
        model, _stats = build_model(instance)
        result = run_scenario(
            model,
            spec,
            scenario_id=str(params["scenario_id"]),
            management_unit=str(params.get("management_unit") or "MU"),
            constraint_floor=params.get("constraint_floor"),
            solver=str(params.get("solver", ws3opt.SOLVER_HIGHS)),
        )
        result = write_scenario_result(result, instance / "results")

        def _relative(path: Path) -> str:
            try:
                return str(path.relative_to(context.workdir))
            except ValueError:
                return str(path)

        artifacts = {
            key: _relative(instance / "results" / value) for key, value in result.artifacts.items()
        }
        diagnostics: tuple[Diagnostic, ...] = ()
        if result.status != "optimal":
            diagnostics = (
                Diagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="scenario.status",
                    message=f"Scenario finished with status '{result.status}'.",
                    location=node.id,
                ),
            )
        return ProviderRunResult(
            status=RunStatus.SUCCESS,
            outputs={
                "scenario_results": {
                    "scenario_id": result.scenario_id,
                    "status": result.status,
                    "harvest_volume_total_m3": result.harvest_volume_total_m3,
                    "bird_abundance_total": result.bird_abundance_total,
                }
            },
            artifacts=artifacts,
            diagnostics=diagnostics,
            data={"provenance": result.provenance},
        )


def provider_factory() -> WbiProvider:
    """Return the WBI provider for FreshForge entry-point discovery."""
    return WbiProvider()
