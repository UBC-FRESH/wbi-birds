from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from wbi_birds.regression import fit_poisson_glm

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN = (
    REPO_ROOT / "external" / "wbi-ebird-data" / "derived" / "rbnu-legacy" / "rbnu_legacy_design.csv"
)
REFERENCE = Path(__file__).parent / "fixtures" / "legacy_rbnu_reference.json"

pytestmark = pytest.mark.skipif(
    not DESIGN.is_file(),
    reason="private eBird data submodule not initialised (external/wbi-ebird-data)",
)


def test_legacy_rbnu_fit_reproduces_2019_reference() -> None:
    """The native regression reproduces the 2019 RBNU fit on the reconstructed matrix."""
    frame = pd.read_csv(DESIGN)
    result = fit_poisson_glm(
        frame[["softwood", "hardwood", "age"]].to_numpy(),
        frame["observation_count"].to_numpy(),
        ("softwood", "hardwood", "age"),
    )
    target = json.loads(REFERENCE.read_text(encoding="utf-8"))["r_2019_reference"]
    for term, expected in target["coefficients"].items():
        assert result.coefficients[term] == pytest.approx(expected, rel=1e-3)
    assert abs(result.n - target["n"]) <= 5
    assert abs(result.residual_deviance - target["residual_deviance"]) < 1.0
    assert abs(result.null_deviance - target["null_deviance"]) < 1.0


def test_reconstructed_reference_is_deterministic() -> None:
    """A fresh fit matches the recorded reconstructed reference tightly."""
    if not DESIGN.is_file():  # pragma: no cover - guarded by pytestmark
        pytest.skip("private data missing")
    frame = pd.read_csv(DESIGN)
    result = fit_poisson_glm(
        frame[["softwood", "hardwood", "age"]].to_numpy(),
        frame["observation_count"].to_numpy(),
        ("softwood", "hardwood", "age"),
    )
    target = json.loads(REFERENCE.read_text(encoding="utf-8"))["reconstructed_reference"]
    for term, expected in target["coefficients"].items():
        assert result.coefficients[term] == pytest.approx(expected, rel=1e-6)
    assert result.n == target["n"]
    assert result.residual_deviance == pytest.approx(target["residual_deviance"], rel=1e-6)
