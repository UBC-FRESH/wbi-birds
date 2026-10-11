"""Scenario and result schemas (E-P2.3).

Pydantic models for the ε-constraint scenario grid and its result records.
Serialized as JSON or YAML; consumed by the E-P3 runner and evidence manifests.
"""

from __future__ import annotations

from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SolverBackend = Literal["highs", "gurobi"]
ScenarioStatus = Literal["optimal", "infeasible", "unbounded", "error"]


class SolverConfig(BaseModel):
    """Solver selection for a scenario run."""

    model_config = ConfigDict(extra="forbid")

    backend: SolverBackend = "highs"
    options: dict[str, Any] = Field(default_factory=dict)


class EvenFlowConfig(BaseModel):
    """Admissible even-flow variation on the targeted harvest output."""

    model_config = ConfigDict(extra="forbid")

    epsilon: float = Field(gt=0.0, le=1.0)


class ScenarioSpec(BaseModel):
    """One ε-constraint scenario for one management unit."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9\-_.]*$")
    management_unit: str = Field(min_length=1)
    species: list[str] = Field(min_length=1)
    epsilon_level: float = Field(
        ge=0.0,
        le=1.0,
        description="Interpolation between nadir (0.0) and nirvana (1.0) bird-abundance levels.",
    )
    bird_abundance_floor: float | None = Field(
        default=None,
        description="ε-constraint RHS (None = nadir / unconstrained).",
    )
    horizon_years: int = Field(gt=0)
    utilization: float = Field(gt=0.0, le=1.0)
    even_flow: EvenFlowConfig
    solver: SolverConfig = Field(default_factory=SolverConfig)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("species")
    @classmethod
    def _species_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("species entries must be unique")
        return value


class SolverResult(BaseModel):
    """Solver-reported outcome for one scenario."""

    model_config = ConfigDict(extra="forbid")

    backend: SolverBackend
    backend_version: str = ""
    status_raw: str = ""
    runtime_seconds: float | None = Field(default=None, ge=0.0)


class ScenarioResult(BaseModel):
    """Results for one executed ε-constraint scenario."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    management_unit: str
    status: ScenarioStatus
    harvest_volume_m3_by_period: list[float] = Field(default_factory=list)
    bird_abundance_by_period: list[float] = Field(default_factory=list)
    harvest_volume_total_m3: float | None = Field(default=None, ge=0.0)
    bird_abundance_total: float | None = None
    solver: SolverResult
    artifacts: dict[str, str] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)
    engine_version: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)


class ScenarioSet(BaseModel):
    """An ordered per-management-unit ε-scenario set."""

    model_config = ConfigDict(extra="forbid")

    management_unit: str = Field(min_length=1)
    species: list[str] = Field(min_length=1)
    scenarios: list[ScenarioSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistency(self) -> ScenarioSet:
        ids = [scenario.id for scenario in self.scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError("scenario ids must be unique within a set")
        for scenario in self.scenarios:
            if scenario.management_unit != self.management_unit:
                raise ValueError(
                    f"scenario '{scenario.id}' management_unit differs from the set's "
                    f"({scenario.management_unit!r} != {self.management_unit!r})"
                )
        levels = [scenario.epsilon_level for scenario in self.scenarios]
        if levels != sorted(levels):
            raise ValueError("scenarios must be ordered by non-decreasing epsilon_level")
        return self


def dump_yaml(model: BaseModel) -> str:
    """Serialize a schema model to YAML (deterministic field order)."""
    return yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False)


def load_yaml(text: str, model_type: type[BaseModel]) -> BaseModel:
    """Load a schema model from YAML text."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("expected a YAML mapping")
    return model_type.model_validate(data)
