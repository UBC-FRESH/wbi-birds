from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from wbi_birds.mapping import load_ws3_sections, stage_ws3_sections
from wbi_birds.model import build_model

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "femic_ws3_bundle"
INSTANCE_FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"
FIXTURE_MODEL = "tsa24_clipped"


@pytest.fixture
def fixture_model(tmp_path: Path):
    """A built ws3 model on the tsa24_clipped fixture instance."""
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    bundle = load_ws3_sections(FIXTURE_DIR, FIXTURE_MODEL)
    stage_ws3_sections(bundle, instance)
    model, _stats = build_model(instance)
    return model
