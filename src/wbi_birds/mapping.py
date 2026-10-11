"""femic -> engine instance mapping (E-P2.2).

Thin file-contract glue: femic produces ws3 Woodstock section files
(`.lan/.are/.yld/.act/.trn` via `femic.ws3_bridge`); the engine stages them into
an instance's `inputs/ws3/`. No femic imports — coupling is by file contract
only (see `planning/femic-map.md`).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

SECTION_SUFFIXES = ("lan", "are", "yld", "act", "trn")


class MappingError(ValueError):
    """Raised when a femic-produced bundle does not satisfy the file contract."""


@dataclass(frozen=True)
class Ws3SectionBundle:
    """Paths to a femic-produced ws3 Woodstock section-file set."""

    model_name: str
    directory: Path
    lan: Path
    are: Path
    yld: Path
    act: Path
    trn: Path


def load_ws3_sections(directory: Path | str, model_name: str) -> Ws3SectionBundle:
    """Validate and reference a femic-produced ws3 section-file set.

    Checks: directory exists; each of the five section files exists, is
    non-empty, and contains at least one ``*`` record.
    """
    root = Path(directory)
    if not root.is_dir():
        raise MappingError(f"Bundle directory not found: {root}")
    paths: dict[str, Path] = {}
    for suffix in SECTION_SUFFIXES:
        path = root / f"{model_name}.{suffix}"
        if not path.is_file():
            raise MappingError(f"Missing ws3 section file: {path}")
        if path.stat().st_size == 0:
            raise MappingError(f"Empty ws3 section file: {path}")
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
        if "*" not in head:
            raise MappingError(f"Not a Woodstock section file (no '*' records): {path}")
        paths[suffix] = path
    return Ws3SectionBundle(
        model_name=model_name,
        directory=root,
        lan=paths["lan"],
        are=paths["are"],
        yld=paths["yld"],
        act=paths["act"],
        trn=paths["trn"],
    )


def stage_ws3_sections(bundle: Ws3SectionBundle, instance_root: Path | str) -> dict[str, str]:
    """Copy a femic bundle into ``<instance>/inputs/ws3/``.

    Returns a mapping of section suffix -> staged path relative to the instance
    root (for manifest/provenance recording).
    """
    root = Path(instance_root)
    target = root / "inputs" / "ws3"
    target.mkdir(parents=True, exist_ok=True)
    staged: dict[str, str] = {}
    for suffix in SECTION_SUFFIXES:
        source: Path = getattr(bundle, suffix)
        destination = target / source.name
        shutil.copyfile(source, destination)
        staged[suffix] = str(destination.relative_to(root))
    return staged
