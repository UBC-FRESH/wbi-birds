"""Biodiversity indicators: guild and composite rows from per-species responses (E-P4.10).

``planning/bird-model-v2-spec.md`` §6. Each species response is a fixed value per
``(development type, age)``, so any **linear combination** of species responses
is also a valid LP bird row. This module builds those rows (guild aggregates and
a weighted composite) as :class:`~wbi_birds.responses.ResponseTable` objects, which
then compile through the existing single-row machinery with no runner change.

Non-separable diversity metrics (expected richness, Shannon) are **not** LP rows:
they depend on the joint composition of the landscape. They are computed after
solving, from a matrix of per-species realised series, by :func:`diversity_metrics`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from wbi_birds.registry import GUILDS, SUITE_GUILDS
from wbi_birds.responses import ResponseTable


class IndicatorError(ValueError):
    """Raised when indicator weights or inputs are invalid."""


def _check_members(tables: Mapping[str, ResponseTable], codes: Sequence[str]) -> None:
    missing = [code for code in codes if code not in tables]
    if missing:
        raise IndicatorError(f"no response table for member species: {', '.join(missing)}")


def build_indicator_response(
    tables: Mapping[str, ResponseTable],
    weights: Mapping[str, float],
    *,
    indicator_code: str,
    source: Mapping[str, Any] | None = None,
) -> ResponseTable:
    """Weighted linear combination of species responses as one indicator row.

    ``weights`` maps species code to a non-negative weight. Every state present in
    every member table is evaluated; states must agree across members (the same
    planning state space), otherwise the call raises.
    """
    if not weights:
        raise IndicatorError("indicator weights must not be empty")
    if any(value < 0 or not math.isfinite(value) for value in weights.values()):
        raise IndicatorError("indicator weights must be finite and non-negative")
    _check_members(tables, list(weights))
    members = {code: tables[code] for code in weights}
    states = None
    for code, table in members.items():
        keys = set(table.values)
        if states is None:
            states = keys
        elif keys != states:
            raise IndicatorError(
                f"species '{code}' is not on the same state space as the other members"
            )
    assert states is not None
    values = {
        state: float(sum(weights[code] * members[code].values[state] for code in weights))
        for state in states
    }
    sd_values: dict[Any, float] = {}
    if all(all(state in table.sd for state in states) for table in members.values()):
        # Independent-error assumption: variance of a weighted sum is sum of w^2 var.
        for state in states:
            variance = sum((weights[code] * members[code].sd[state]) ** 2 for code in weights)
            sd_values[state] = float(math.sqrt(variance))
    provenance = {
        "indicator": indicator_code,
        "weights": {code: float(weights[code]) for code in sorted(weights)},
        "members": sorted(weights),
        "combination": "weighted linear sum of species responses (LP-linear row)",
        **dict(source or {}),
    }
    return ResponseTable(
        species_code=indicator_code,
        values=values,
        sd=sd_values,
        source=provenance,
    )


def guild_weights(
    guild: str,
    *,
    members: Sequence[str] | None = None,
    scheme: str = "sum",
) -> dict[str, float]:
    """Member weights for a guild aggregate.

    ``scheme="sum"`` (default) weights each member 1 — the guild row is the summed
    abundance response of its members. ``scheme="mean"`` divides by the member count
    so the guild row is an average response per species.
    """
    if guild not in GUILDS:
        raise IndicatorError(f"unknown guild '{guild}' (expected one of {GUILDS})")
    codes = [code for code, g in SUITE_GUILDS.items() if g == guild]
    if members is not None:
        codes = [code for code in codes if code in set(members)]
    if not codes:
        raise IndicatorError(f"guild '{guild}' has no member species in this suite")
    if scheme not in {"sum", "mean"}:
        raise IndicatorError("scheme must be 'sum' or 'mean'")
    weight = 1.0 if scheme == "sum" else 1.0 / len(codes)
    return dict.fromkeys(codes, weight)


def guild_indicators(
    tables: Mapping[str, ResponseTable],
    *,
    scheme: str = "sum",
    guilds: Sequence[str] = GUILDS,
) -> dict[str, ResponseTable]:
    """One indicator row per guild that has member species present in ``tables``."""
    rows: dict[str, ResponseTable] = {}
    for guild in guilds:
        members = [code for code, g in SUITE_GUILDS.items() if g == guild and code in tables]
        if not members:
            continue
        weights = guild_weights(guild, members=members, scheme=scheme)
        rows[guild] = build_indicator_response(
            tables,
            weights,
            indicator_code=f"guild:{guild}",
            source={"guild": guild, "scheme": scheme},
        )
    return rows


def composite_weights(
    codes: Sequence[str],
    *,
    scheme: str = "equal",
    conservation_weight: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Weights for a composite community index.

    ``equal``: each species weight 1. ``guild_balanced``: each guild contributes
    equally in total (members within a guild share 1/|guild|). ``custom``: use
    ``conservation_weight`` directly. Weights are returned unnormalised so the LP
    value is interpretable as a weighted abundance index; the chosen scheme is
    recorded in the indicator's provenance.
    """
    if not codes:
        raise IndicatorError("composite index needs at least one species")
    if scheme == "equal":
        return dict.fromkeys(codes, 1.0)
    if scheme == "guild_balanced":
        counts: dict[str, int] = {}
        for code in codes:
            guild = SUITE_GUILDS.get(code)
            if guild is None:
                raise IndicatorError(f"species '{code}' has no guild in the registry")
            counts[guild] = counts.get(guild, 0) + 1
        return {code: 1.0 / counts[SUITE_GUILDS[code]] for code in codes}
    if scheme == "custom":
        if not conservation_weight:
            raise IndicatorError("custom scheme needs conservation_weight")
        missing = [code for code in codes if code not in conservation_weight]
        if missing:
            raise IndicatorError(f"custom weights missing species: {', '.join(missing)}")
        return {code: float(conservation_weight[code]) for code in codes}
    raise IndicatorError(f"unknown composite scheme '{scheme}'")


def composite_indicator(
    tables: Mapping[str, ResponseTable],
    *,
    scheme: str = "equal",
    conservation_weight: Mapping[str, float] | None = None,
    indicator_code: str = "composite",
) -> ResponseTable:
    """Weighted composite community index as one LP-linear indicator row."""
    codes = sorted(tables)
    weights = composite_weights(codes, scheme=scheme, conservation_weight=conservation_weight)
    return build_indicator_response(
        tables,
        weights,
        indicator_code=indicator_code,
        source={"scheme": scheme},
    )


def diversity_metrics(series: np.ndarray, *, species: Sequence[str]) -> dict[str, np.ndarray]:
    """Post-solve, non-separable diversity diagnostics from realised species series.

    ``series`` has shape ``(n_species, n_periods)`` and holds realised per-species
    abundance per period (from the solved schedule). Returns per-period expected
    richness (effective number of species, exp of Shannon entropy is reported
    separately) and Shannon entropy. These are diagnostics, never LP rows.
    """
    matrix = np.asarray(series, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != len(species):
        raise IndicatorError("series must be (n_species, n_periods) matching species")
    if np.any(matrix < 0) or not np.all(np.isfinite(matrix)):
        raise IndicatorError("realised series must be finite and non-negative")
    totals = matrix.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        proportions = np.where(totals > 0, matrix / totals, 0.0)
        logs = np.where(proportions > 0, np.log(proportions), 0.0)
    shannon = -np.sum(proportions * logs, axis=0)
    present = np.sum(matrix > 0, axis=0).astype(float)
    return {
        "richness": present,
        "shannon": shannon,
        "effective_species": np.exp(shannon),
    }
