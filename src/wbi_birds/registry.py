"""Species/guild registry (E-P4.2).

Canonical suite per the manuscript design (P2.3): nine boreal landbird species
across four guilds, with eBird taxonomy-code validation against the snapshot in
:mod:`wbi_birds.taxonomy`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from wbi_birds.instance import Issue, _issue  # reuse finding type/helpers
from wbi_birds.taxonomy import TAXONOMY_SNAPSHOT

GUILDS: tuple[str, ...] = ("mature_conifer", "mixedwood", "early_seral", "cavity")

SUITE_GUILDS: dict[str, str] = {
    "rebnut": "mature_conifer",
    "borchi2": "mature_conifer",
    "gockin": "mature_conifer",
    "brncre": "mature_conifer",
    "yerwar": "mixedwood",
    "swathr": "mixedwood",
    "whtspa": "early_seral",
    "tenwar": "early_seral",
    "yebsap": "cavity",
}


@dataclass(frozen=True)
class SpeciesEntry:
    """One species in a registry."""

    code: str
    common: str | None = None
    scientific: str | None = None
    guild: str | None = None


@dataclass(frozen=True)
class SpeciesRegistry:
    """A species/guild registry (canonical or instance-loaded)."""

    species: tuple[SpeciesEntry, ...]
    guilds: tuple[str, ...]

    def codes(self) -> tuple[str, ...]:
        return tuple(entry.code for entry in self.species)

    def by_guild(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for entry in self.species:
            if entry.guild:
                grouped.setdefault(entry.guild, []).append(entry.code)
        return {guild: tuple(codes) for guild, codes in grouped.items()}


def manuscript_suite() -> SpeciesRegistry:
    """The canonical nine-species suite (manuscript P2.3)."""
    entries = tuple(
        SpeciesEntry(
            code=code,
            common=TAXONOMY_SNAPSHOT[code]["common"],
            scientific=TAXONOMY_SNAPSHOT[code]["scientific"],
            guild=guild,
        )
        for code, guild in SUITE_GUILDS.items()
    )
    return SpeciesRegistry(species=entries, guilds=GUILDS)


def load_registry(instance_root: Path | str) -> SpeciesRegistry:
    """Load the registry from an instance's ``config/species.yaml``."""
    path = Path(instance_root) / "config" / "species.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Species config is not a mapping: {path}")
    entries: list[SpeciesEntry] = []
    for item in data.get("species") or []:
        if not isinstance(item, dict) or not item.get("code"):
            raise ValueError(f"Invalid species entry in {path}: {item!r}")
        code = str(item["code"])
        snapshot = TAXONOMY_SNAPSHOT.get(code, {})
        entries.append(
            SpeciesEntry(
                code=code,
                common=item.get("common"),
                scientific=item.get("scientific", snapshot.get("scientific")),
                guild=item.get("guild"),
            )
        )
    guilds = tuple(str(g) for g in (data.get("guilds") or []))
    return SpeciesRegistry(species=tuple(entries), guilds=guilds)


def validate_taxonomy(registry: SpeciesRegistry) -> list[Issue]:
    """Taxonomy-code and naming checks for a registry.

    - unknown code -> error
    - common-name mismatch vs the snapshot -> warning
    - guild not in the canonical guild list -> warning
    """
    issues: list[Issue] = []
    for entry in registry.species:
        snapshot = TAXONOMY_SNAPSHOT.get(entry.code)
        if snapshot is None:
            issues.append(
                _issue(
                    "error",
                    "species.unknown_code",
                    f"Species code '{entry.code}' is not in the eBird taxonomy snapshot.",
                )
            )
            continue
        if entry.common and entry.common.lower() != snapshot["common"].lower():
            issues.append(
                _issue(
                    "warning",
                    "species.common_mismatch",
                    f"Common name '{entry.common}' does not match taxonomy "
                    f"'{snapshot['common']}' for code '{entry.code}'.",
                )
            )
        if entry.guild and entry.guild not in GUILDS:
            issues.append(
                _issue(
                    "warning",
                    "species.guild_unknown",
                    f"Guild '{entry.guild}' for code '{entry.code}' is not a canonical guild.",
                )
            )
    return issues
