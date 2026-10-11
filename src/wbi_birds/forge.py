"""FreshForge provider for the WBI birds engine.

Plan-only (metadata + validation) for now; execution hooks (``run_node``) arrive
with ROADMAP E-P3–E-P5. Registered via the ``freshforge.providers`` entry point
as provider ID ``wbi``.
"""

from __future__ import annotations

from collections.abc import Sequence

from freshforge.providers import NodeTypeMetadata, ProviderMetadata
from freshforge.records import Diagnostic, DiagnosticSeverity, WorkflowNode

PROVIDER_ID = "wbi"
PROVIDER_VERSION = "0.1.0a1"

NODE_TYPES: tuple[NodeTypeMetadata, ...] = (
    NodeTypeMetadata(
        id="ingest_ebd",
        name="Ingest eBird data",
        description="Filter the private EBD/SED extract to the species suite and derive point-level tables.",
        outputs=("derived_tables",),
        parameters=("species_suite", "months"),
        artifacts=("report",),
    ),
    NodeTypeMetadata(
        id="fit_antifunction",
        name="Fit anticipation functions",
        description="Fit per-species GLMs (counts ~ softwood/hardwood biomass + age) and export coefficients.",
        inputs=("derived_tables",),
        outputs=("coefficients",),
        parameters=("family",),
        artifacts=("coefficients",),
    ),
    NodeTypeMetadata(
        id="compile_instance",
        name="Compile instance",
        description="Compile a per-management-unit instance from femic outputs + coefficients (data-contract layout).",
        inputs=("coefficients",),
        outputs=("instance_root",),
        parameters=("femic_bundle", "management_unit"),
        artifacts=("instance",),
    ),
    NodeTypeMetadata(
        id="build_model",
        name="Build ws3 model",
        description="Build the ws3 forest-estate model (Model I, even-flow) for the instance.",
        inputs=("instance_root",),
        outputs=("forest_model",),
        parameters=("solver",),
    ),
    NodeTypeMetadata(
        id="run_scenarios",
        name="Run scenario grid",
        description="Run the ε-constraint scenario grid and write scenario result tables.",
        inputs=("forest_model",),
        outputs=("scenario_results",),
        parameters=("epsilon_steps", "mode"),
        artifacts=("results",),
    ),
    NodeTypeMetadata(
        id="compute_frontiers",
        name="Compute frontiers",
        description="Compute Pareto frontier + marginal opportunity-cost metrics from scenario results.",
        inputs=("scenario_results",),
        outputs=("frontiers",),
    ),
    NodeTypeMetadata(
        id="verify_parity",
        name="Verify legacy parity",
        description="Compare engine results against legacy RBNU/5-TSA outputs within recorded tolerances.",
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
                                f"Node is missing required provider-declared {field_name} key '{key}'."
                            ),
                            location=f"{location}.{field_name}.{key}",
                        )
                    )
        return diagnostics


def provider_factory() -> WbiProvider:
    """Return the WBI provider for FreshForge entry-point discovery."""
    return WbiProvider()
