from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from wbi_birds.instance import ERROR, validate_instance
from wbi_birds.mapping import MappingError, load_ws3_sections, stage_ws3_sections

FIXTURE = Path(__file__).parent / "fixtures" / "femic_ws3_bundle"
INSTANCE_FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"
MODEL = "tsa24_clipped"


def test_load_bundle() -> None:
    bundle = load_ws3_sections(FIXTURE, MODEL)
    assert bundle.model_name == MODEL
    assert bundle.lan.name == f"{MODEL}.lan"
    assert bundle.trn.name == f"{MODEL}.trn"


def test_load_bundle_missing_directory() -> None:
    with pytest.raises(MappingError, match="Bundle directory not found"):
        load_ws3_sections(FIXTURE / "nope", MODEL)


def test_load_bundle_missing_section(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    shutil.copytree(FIXTURE, bundle_dir)
    (bundle_dir / f"{MODEL}.trn").unlink()
    with pytest.raises(MappingError, match="Missing ws3 section file"):
        load_ws3_sections(bundle_dir, MODEL)


def test_empty_section_rejected(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    shutil.copytree(FIXTURE, bundle_dir)
    (bundle_dir / f"{MODEL}.act").write_text("")
    with pytest.raises(MappingError, match="Empty ws3 section file"):
        load_ws3_sections(bundle_dir, MODEL)


def test_stage_into_instance_and_validate(tmp_path: Path) -> None:
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    bundle = load_ws3_sections(FIXTURE, MODEL)
    staged = stage_ws3_sections(bundle, instance)
    assert set(staged) == {"lan", "are", "yld", "act", "trn"}
    for rel in staged.values():
        assert (instance / rel).is_file()
    errors = [issue for issue in validate_instance(instance) if issue.severity == ERROR]
    assert errors == [], [str(issue) for issue in errors]
