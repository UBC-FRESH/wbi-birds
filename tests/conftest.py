from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from wbi_birds.mapping import load_ws3_sections, stage_ws3_sections
from wbi_birds.model import build_model

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "femic_ws3_bundle"
INSTANCE_FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"
FIXTURE_MODEL = "tsa24_clipped"

# FreshForge colourises CLI output when FORCE_COLOR / CLICOLOR_FORCE is present
# (e.g. inside Jupyter / VS Code kernels) - even a value of "0" forces colour in
# Rich - which breaks JSON parsing. Strip them for machine-readable runs.
FRESH_PROCESS_ENV = {
    key: value for key, value in os.environ.items() if key not in {"FORCE_COLOR", "CLICOLOR_FORCE"}
}


@pytest.fixture
def fixture_instance(tmp_path: Path) -> Path:
    """A fixture instance directory with the tsa24_clipped bundle staged."""
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    bundle = load_ws3_sections(FIXTURE_DIR, FIXTURE_MODEL)
    stage_ws3_sections(bundle, instance)
    return instance


@pytest.fixture
def fixture_model(fixture_instance: Path):
    """A built ws3 model on the tsa24_clipped fixture instance."""
    model, _stats = build_model(fixture_instance)
    return model
