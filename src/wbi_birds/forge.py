"""FreshForge provider for the WBI birds engine.

Plan-only (metadata + validation) for now; execution hooks (``run_node``) arrive
with planning phases E-P3 to E-P5. Registered via the ``freshforge.providers`` entry point
as provider ID ``wbi``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from freshforge.providers import NodeTypeMetadata, ProviderMetadata
from freshforge.records import (
    Diagnostic,
    DiagnosticSeverity,
    ProviderRunResult,
    RunStatus,
    WorkflowNode,
)
from ws3 import opt as ws3opt

from wbi_birds.bird import load_coefficients
from wbi_birds.fit import fit_poisson_glm, stage_coefficients, update_instance_coefficients
from wbi_birds.ingest import IngestSpec, ingest_ebd
from wbi_birds.mapping import load_ws3_sections, locate_ws3_bundle, stage_ws3_sections
from wbi_birds.model import build_model
from wbi_birds.parity import compare_instance_results, write_report
from wbi_birds.registry import load_registry
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
        parameters=(
            "instance",
            "ebd",
            "species",
            "months",
            "complete_checklists_only",
            "out",
        ),
        artifacts=("derived_table", "provenance"),
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
        parameters=("instance", "mode", "coefficients", "covariates", "species"),
        artifacts=("coefficients",),
    ),
    NodeTypeMetadata(
        id="compile_instance",
        name="Compile instance",
        description=(
            "Compile a per-management-unit instance from femic outputs + "
            "coefficients (data-contract layout)."
        ),
        inputs=(),
        outputs=("instance_root",),
        parameters=("instance", "femic_bundle", "management_unit", "model_name"),
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
            "bird_species",
            "measure_scope",
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
        outputs=("parity_report",),
        parameters=("instance", "reference", "label", "strict"),
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
            if node_type.id == "compile_instance":
                return self._run_compile_instance(node, params, context)
            if node_type.id == "ingest_ebd":
                return self._run_ingest_ebd(node, params, context)
            if node_type.id == "fit_antifunction":
                return self._run_fit_antifunction(node, params, context)
            if node_type.id == "verify_parity":
                return self._run_verify_parity(node, params, context)
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
        bird_species = params.get("bird_species")
        bird_coefficients = load_coefficients(instance, str(bird_species)) if bird_species else None
        measure_scope = str(
            params.get("measure_scope") or ("landscape" if bird_species else "harvest")
        )
        spec = ProblemSpec(
            objective_expr=str(params["objective_expr"]),
            constraint_row=str(params.get("constraint_row", "constraint")),
            constraint_expr=str(params["constraint_expr"]),
            measure_scope=measure_scope,  # type: ignore[arg-type]
            bird_coefficients=bird_coefficients,
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

        artifacts = {
            key: self._relative_to_workdir(instance / "results" / value, context)
            for key, value in result.artifacts.items()
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

    def _run_ingest_ebd(
        self, node: WorkflowNode, params: dict[str, Any], context: Any
    ) -> ProviderRunResult:
        instance = self._resolve_instance(params, context)
        if "ebd" not in params:
            raise ValueError("Node parameters must provide 'ebd' (path to the private EBD extract)")
        ebd_path = Path(context.resolve_path(str(params["ebd"])))
        registry = load_registry(instance)
        species = tuple(str(code) for code in params.get("species") or registry.codes())
        months = tuple(int(month) for month in params.get("months", (5, 6, 7, 8)))
        out_path = instance / "bird" / "derived" / str(params.get("out", "ebd_suite.csv"))
        summary = ingest_ebd(
            IngestSpec(
                ebd_path=ebd_path,
                out_csv=out_path,
                species=species,
                months=months,
                complete_checklists_only=bool(params.get("complete_checklists_only", False)),
            )
        )
        sidecar = out_path.with_name(out_path.name + ".provenance.json")
        return ProviderRunResult(
            status=RunStatus.SUCCESS,
            outputs={
                "derived_tables": {
                    "rows_kept": summary.rows_kept,
                    "per_species": summary.per_species,
                }
            },
            artifacts={
                "derived_table": self._relative_to_workdir(out_path, context),
                "provenance": self._relative_to_workdir(sidecar, context),
            },
            data={"filters": summary.filters, "rows_scanned": summary.rows_scanned},
        )

    def _run_fit_antifunction(
        self, node: WorkflowNode, params: dict[str, Any], context: Any
    ) -> ProviderRunResult:
        instance = self._resolve_instance(params, context)
        mode = str(params.get("mode", "provided"))
        if mode == "provided":
            if "coefficients" not in params:
                raise ValueError("'coefficients' path is required for mode=provided")
            source = Path(context.resolve_path(str(params["coefficients"])))
            path = stage_coefficients(source, instance)
            outputs = {"coefficients": {"mode": "provided"}}
        elif mode == "poisson":
            for required in ("covariates", "species"):
                if required not in params:
                    raise ValueError(f"'{required}' is required for mode=poisson")
            covariates = Path(context.resolve_path(str(params["covariates"])))
            result = fit_poisson_glm(covariates)
            path = update_instance_coefficients(
                instance,
                str(params["species"]),
                result.coefficients,
                fit_note="poisson_mle",
            )
            outputs = {
                "coefficients": {
                    "mode": "poisson",
                    "converged": result.converged,
                    "n_observations": result.n_observations,
                    "values": result.coefficients.to_constants(),
                }
            }
        else:
            raise ValueError(f"Unknown fit mode '{mode}' (expected 'provided' or 'poisson')")
        return ProviderRunResult(
            status=RunStatus.SUCCESS,
            outputs=outputs,
            artifacts={"coefficients": self._relative_to_workdir(path, context)},
            data={"instance": str(instance)},
        )

    def _run_verify_parity(
        self, node: WorkflowNode, params: dict[str, Any], context: Any
    ) -> ProviderRunResult:
        instance = self._resolve_instance(params, context)
        if "reference" not in params:
            raise ValueError(
                "Node parameters must provide 'reference' (long-format reference table)"
            )
        reference = Path(context.resolve_path(str(params["reference"])))
        label = str(params.get("label") or "suite")
        strict = bool(params.get("strict", False))
        report = compare_instance_results(instance, reference)
        artifacts = write_report(report, instance / "results", label=label)
        summary = report.summary()
        diagnostics: list[Diagnostic] = []
        for metric, stats in summary["per_metric"].items():
            if stats["failed"]:
                diagnostics.append(
                    Diagnostic(
                        severity=DiagnosticSeverity.WARNING,
                        code="parity.failed",
                        message=(
                            f"Parity metric '{metric}': {stats['failed']} of {stats['n']} "
                            "records failed tolerance."
                        ),
                        location=node.id,
                    )
                )
        status = RunStatus.SUCCESS
        if strict and summary["n_failed"] > 0:
            status = RunStatus.FAILED
            diagnostics.append(
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="parity.strict",
                    message=f"Strict parity mode: {summary['n_failed']} record(s) failed.",
                    location=node.id,
                )
            )
        return ProviderRunResult(
            status=status,
            outputs={"parity_report": summary},
            artifacts={
                "report_json": self._relative_to_workdir(
                    instance / "results" / artifacts["json"], context
                ),
                "report_markdown": self._relative_to_workdir(
                    instance / "results" / artifacts["markdown"], context
                ),
            },
            diagnostics=tuple(diagnostics),
            data={"reference": str(reference), "label": label, "strict": strict},
        )

    @staticmethod
    def _relative_to_workdir(path: Path, context: Any) -> str:
        try:
            return str(path.relative_to(context.workdir))
        except ValueError:
            return str(path)

    def _run_compile_instance(
        self, node: WorkflowNode, params: dict[str, Any], context: Any
    ) -> ProviderRunResult:
        instance = self._resolve_instance(params, context)
        if "femic_bundle" not in params:
            raise ValueError(
                "Node parameters must provide 'femic_bundle' (a directory of ws3 section files)"
            )
        bundle_dir = Path(context.resolve_path(str(params["femic_bundle"])))
        model_name = str(params.get("model_name") or locate_ws3_bundle(bundle_dir))
        bundle = load_ws3_sections(bundle_dir, model_name)
        staged = stage_ws3_sections(bundle, instance)
        management_unit = params.get("management_unit")
        if management_unit:
            self._update_management_unit(instance, str(management_unit))
        return ProviderRunResult(
            status=RunStatus.SUCCESS,
            outputs={"instance_root": str(instance)},
            artifacts={"instance": self._relative_to_workdir(instance, context)},
            data={
                "model_name": model_name,
                "staged_sections": staged,
                "management_unit": str(management_unit) if management_unit else None,
            },
        )

    @staticmethod
    def _update_management_unit(instance: Path, management_unit: str) -> None:
        run_path = instance / "config" / "run.yaml"
        run = yaml.safe_load(run_path.read_text(encoding="utf-8"))
        if not isinstance(run, dict):
            raise ValueError(f"Run config is not a mapping: {run_path}")
        run["management_unit"] = {"id": management_unit, "name": management_unit}
        run_path.write_text(yaml.safe_dump(run, sort_keys=False), encoding="utf-8")


def provider_factory() -> WbiProvider:
    """Return the WBI provider for FreshForge entry-point discovery."""
    return WbiProvider()
