from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from wbi_birds.mapping import load_ws3_sections, locate_ws3_bundle, stage_ws3_sections
from wbi_birds.model import ModelBuildError, build_model

FIXTURE = Path(__file__).parent / "fixtures" / "femic_ws3_bundle"
INSTANCE_FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"
MODEL = "tsa24_clipped"


def _instance_with_bundle(tmp_path: Path) -> Path:
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    bundle = load_ws3_sections(FIXTURE, MODEL)
    stage_ws3_sections(bundle, instance)
    return instance


def test_locate_ws3_bundle() -> None:
    assert locate_ws3_bundle(FIXTURE) == MODEL


def test_locate_ws3_bundle_rejects_multiple(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    shutil.copytree(FIXTURE, bundle_dir)
    for suffix in ("lan", "are", "yld", "act", "trn"):
        shutil.copy(bundle_dir / f"{MODEL}.{suffix}", bundle_dir / f"other.{suffix}")
    with pytest.raises(ValueError, match="Multiple ws3 bundles"):
        locate_ws3_bundle(bundle_dir)


def test_build_model(tmp_path: Path) -> None:
    instance = _instance_with_bundle(tmp_path)
    model, stats = build_model(instance)
    assert stats.model_name == MODEL
    assert stats.base_year == 2020
    assert stats.horizon_periods == 16  # 80 years / 5-year periods
    assert stats.period_length_years == 5
    assert stats.dtype_count > 0
    assert stats.action_count > 0
    assert stats.curve_count > 0
    assert stats.to_dict()["model_name"] == MODEL
    assert model.model_name == MODEL


def test_build_model_respects_model_block(tmp_path: Path) -> None:
    instance = _instance_with_bundle(tmp_path)
    run = instance / "config" / "run.yaml"
    run.write_text(
        run.read_text() + "model: {base_year: 2015, period_length_years: 10, max_age: 200}\n"
    )
    _model, stats = build_model(instance)
    assert stats.base_year == 2015
    assert stats.period_length_years == 10
    assert stats.horizon_periods == 8  # 80 years / 10-year periods


def test_build_model_rejects_bad_horizon(tmp_path: Path) -> None:
    instance = _instance_with_bundle(tmp_path)
    run = instance / "config" / "run.yaml"
    run.write_text(run.read_text().replace("horizon_years: 80", "horizon_years: 77"))
    with pytest.raises(ModelBuildError, match="multiple"):
        build_model(instance)
