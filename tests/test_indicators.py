from __future__ import annotations

import math

import numpy as np
import pytest

from wbi_birds.indicators import (
    IndicatorError,
    build_indicator_response,
    composite_indicator,
    composite_weights,
    diversity_metrics,
    guild_indicators,
    guild_weights,
)
from wbi_birds.registry import GUILDS, SUITE_GUILDS
from wbi_birds.responses import ResponseTable

STATES = [(("dt", "1"), 40), (("dt", "1"), 80), (("dt", "2"), 40)]


def _table(code: str, base: float) -> ResponseTable:
    return ResponseTable(
        species_code=code,
        values={state: base + index for index, state in enumerate(STATES)},
        sd=dict.fromkeys(STATES, 0.1),
    )


def _suite() -> dict[str, ResponseTable]:
    # rebnut + borchi2 are mature_conifer; yerwar is mixedwood; whtspa is early_seral.
    return {
        "rebnut": _table("rebnut", 1.0),
        "borchi2": _table("borchi2", 2.0),
        "yerwar": _table("yerwar", 10.0),
        "whtspa": _table("whtspa", 100.0),
    }


def test_weighted_sum_matches_hand_arithmetic() -> None:
    row = build_indicator_response(
        _suite(), {"rebnut": 1.0, "yerwar": 0.5}, indicator_code="custom"
    )
    assert row.values[STATES[0]] == pytest.approx(1.0 + 0.5 * 10.0)
    assert row.values[STATES[2]] == pytest.approx((1.0 + 2.0) + 0.5 * (10.0 + 2.0))


def test_indicator_sd_is_independent_error_sum() -> None:
    row = build_indicator_response(_suite(), {"rebnut": 1.0, "borchi2": 1.0}, indicator_code="pair")
    assert row.sd[STATES[0]] == pytest.approx(math.sqrt(2) * 0.1)


def test_guild_rows_use_registry_membership() -> None:
    rows = guild_indicators(_suite())
    assert set(rows) == {"mature_conifer", "mixedwood", "early_seral"}  # no cavity member present
    conifer = rows["mature_conifer"]
    assert conifer.values[STATES[0]] == pytest.approx(1.0 + 2.0)
    assert conifer.source["guild"] == "mature_conifer"
    assert set(conifer.source["members"]) == {
        code for code, guild in SUITE_GUILDS.items() if guild == "mature_conifer"
    } & set(_suite())


def test_guild_mean_scheme_divides_by_member_count() -> None:
    weights = guild_weights("mature_conifer", members=["rebnut", "borchi2"], scheme="mean")
    assert weights == {"rebnut": 0.5, "borchi2": 0.5}
    rows = guild_indicators(_suite(), scheme="mean")
    assert rows["mature_conifer"].values[STATES[0]] == pytest.approx(1.5)


def test_composite_schemes() -> None:
    suite = _suite()
    equal = composite_indicator(suite, scheme="equal")
    assert equal.values[STATES[0]] == pytest.approx(1.0 + 2.0 + 10.0 + 100.0)
    balanced = composite_weights(sorted(suite), scheme="guild_balanced")
    # mature_conifer has 2 members -> 1/2 each; mixedwood and early_seral have 1 each.
    assert balanced["rebnut"] == pytest.approx(0.5)
    assert balanced["yerwar"] == pytest.approx(1.0)
    custom = composite_indicator(
        suite,
        scheme="custom",
        conservation_weight={"rebnut": 2.0, "borchi2": 0.0, "yerwar": 1.0, "whtspa": 0.0},
    )
    assert custom.values[STATES[0]] == pytest.approx(2.0 * 1.0 + 1.0 * 10.0)


def test_invalid_weights_and_members_are_rejected() -> None:
    suite = _suite()
    with pytest.raises(IndicatorError, match="empty"):
        build_indicator_response(suite, {}, indicator_code="x")
    with pytest.raises(IndicatorError, match="non-negative"):
        build_indicator_response(suite, {"rebnut": -1.0}, indicator_code="x")
    with pytest.raises(IndicatorError, match="no response table"):
        build_indicator_response(suite, {"nope": 1.0}, indicator_code="x")
    with pytest.raises(IndicatorError, match="unknown guild"):
        guild_weights("not_a_guild")
    with pytest.raises(IndicatorError, match="custom"):
        composite_weights(["rebnut"], scheme="custom")


def test_mismatched_state_spaces_are_rejected() -> None:
    suite = _suite()
    suite["rebnut"] = ResponseTable(species_code="rebnut", values={STATES[0]: 1.0}, sd={})
    with pytest.raises(IndicatorError, match="same state space"):
        build_indicator_response(suite, {"rebnut": 1.0, "borchi2": 1.0}, indicator_code="x")


def test_diversity_metrics_match_hand_values() -> None:
    series = np.array([[1.0, 1.0], [1.0, 1.0], [2.0, 0.0]])
    metrics = diversity_metrics(series, species=["a", "b", "c"])
    assert metrics["richness"].tolist() == [3.0, 2.0]
    expected = -(2 * 0.25 * math.log(0.25) + 0.5 * math.log(0.5))
    assert metrics["shannon"][0] == pytest.approx(expected)
    assert metrics["effective_species"][0] == pytest.approx(math.exp(expected))
    assert metrics["shannon"][1] == pytest.approx(math.log(2))


def test_diversity_rejects_bad_series() -> None:
    with pytest.raises(IndicatorError, match="must be"):
        diversity_metrics(np.ones((2, 3)), species=["a", "b", "c"])
    with pytest.raises(IndicatorError, match="non-negative"):
        diversity_metrics(np.array([[-1.0, 1.0]]), species=["a"])


def test_every_suite_species_maps_to_a_declared_guild() -> None:
    assert set(SUITE_GUILDS.values()) <= set(GUILDS)
    assert set(SUITE_GUILDS) == {
        "rebnut",
        "borchi2",
        "gockin",
        "brncre",
        "yerwar",
        "swathr",
        "whtspa",
        "tenwar",
        "yebsap",
    }
