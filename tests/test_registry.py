from __future__ import annotations

import shutil
from pathlib import Path

from wbi_birds.registry import (
    GUILDS,
    SpeciesEntry,
    SpeciesRegistry,
    load_registry,
    manuscript_suite,
    validate_taxonomy,
)
from wbi_birds.taxonomy import TAXONOMY_SNAPSHOT

INSTANCE_FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"


def test_manuscript_suite_matches_taxonomy() -> None:
    registry = manuscript_suite()
    codes = registry.codes()
    assert len(codes) == 9
    assert len(set(codes)) == 9
    assert all(code in TAXONOMY_SNAPSHOT for code in codes)
    assert set(registry.guilds) == set(GUILDS)
    grouped = registry.by_guild()
    assert len(grouped["mature_conifer"]) == 4
    assert len(grouped["mixedwood"]) == 2
    assert len(grouped["early_seral"]) == 2
    assert grouped["cavity"] == ("yebsap",)


def test_manuscript_suite_validates_clean() -> None:
    assert validate_taxonomy(manuscript_suite()) == []


def test_load_registry_fixture() -> None:
    registry = load_registry(INSTANCE_FIXTURE)
    assert set(registry.codes()) == set(TAXONOMY_SNAPSHOT)
    assert set(registry.guilds) == set(GUILDS)
    assert validate_taxonomy(registry) == []


def test_validate_taxonomy_flags_unknown_code_and_name() -> None:
    registry = SpeciesRegistry(
        species=(
            SpeciesEntry(code="notabird", common="Not A Bird", guild="mature_conifer"),
            SpeciesEntry(code="rebnut", common="Wrong Name", guild="mature_conifer"),
            SpeciesEntry(code="borchi2", guild="imaginary_guild"),
        ),
        guilds=GUILDS,
    )
    findings = validate_taxonomy(registry)
    codes = {issue.code for issue in findings}
    assert "species.unknown_code" in codes
    assert "species.common_mismatch" in codes
    assert "species.guild_unknown" in codes
    unknown = next(issue for issue in findings if issue.code == "species.unknown_code")
    assert unknown.severity == "error"
    mismatch = next(issue for issue in findings if issue.code == "species.common_mismatch")
    assert mismatch.severity == "warning"


def test_instance_contains_suite(tmp_path: Path) -> None:
    instance = tmp_path / "instance"
    shutil.copytree(INSTANCE_FIXTURE, instance)
    registry = load_registry(instance)
    assert validate_taxonomy(registry) == []
