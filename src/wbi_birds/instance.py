"""Instance directory contract validation (E-P2.1).

Dependency-light implementation (yaml + hashlib). Pydantic schemas arrive with
E-P2.3; this module enforces the contract in ``planning/data-contract.md``:

- required files and broad schemas (manifest, run/species config, coefficients)
- species <-> coefficient consistency
- checksum verification when declared
- raw-eBird boundary scan (Terms of Use: no raw files inside instances)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from wbi_birds.taxonomy import TAXONOMY_SNAPSHOT

ERROR = "error"
WARNING = "warning"

RAW_EBIRD_SUFFIXES = (".txt", ".zip", ".csv")


@dataclass(frozen=True)
class Issue:
    """One validation finding."""

    severity: str
    code: str
    message: str
    path: str = ""


def _issue(severity: str, code: str, message: str, path: Path | str = "") -> Issue:
    return Issue(severity=severity, code=code, message=message, path=str(path))


def _load_yaml(path: Path) -> tuple[dict[str, Any] | None, Issue | None]:
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        return None, _issue(ERROR, "file.missing", "Required file is missing.", path)
    except (OSError, yaml.YAMLError) as exc:
        return None, _issue(ERROR, "file.unreadable", f"Could not read/parse: {exc}", path)
    if not isinstance(data, dict):
        return None, _issue(ERROR, "file.invalid", "Expected a YAML mapping.", path)
    return data, None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_raw_ebird(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("ebd_") and lowered.endswith(RAW_EBIRD_SUFFIXES)


def _validate_manifest(root: Path, issues: list[Issue]) -> None:
    manifest, issue = _load_yaml(root / "manifest.yaml")
    if issue is not None:
        issues.append(issue)
        return
    assert manifest is not None
    if manifest.get("schema_version") != 1:
        issues.append(
            _issue(
                ERROR,
                "manifest.schema_version",
                "schema_version must be 1.",
                root / "manifest.yaml",
            )
        )
    if not manifest.get("instance_id"):
        issues.append(
            _issue(
                ERROR, "manifest.instance_id", "instance_id is required.", root / "manifest.yaml"
            )
        )
    if not isinstance(manifest.get("provenance"), dict):
        issues.append(
            _issue(
                WARNING,
                "manifest.provenance",
                "provenance block missing or not a mapping.",
                root / "manifest.yaml",
            )
        )
    checksums = manifest.get("checksums")
    if not isinstance(checksums, dict):
        issues.append(
            _issue(
                WARNING,
                "manifest.checksums",
                "checksums block missing or not a mapping.",
                root / "manifest.yaml",
            )
        )
        return
    files = checksums.get("files") or {}
    if not isinstance(files, dict):
        issues.append(
            _issue(
                ERROR,
                "manifest.checksums_files",
                "checksums.files must be a mapping of relative path -> sha256.",
                root / "manifest.yaml",
            )
        )
        return
    for rel, expected in files.items():
        target = root / rel
        if not target.is_file():
            issues.append(
                _issue(ERROR, "checksums.file_missing", f"Checksummed file missing: {rel}", target)
            )
            continue
        actual = _sha256(target)
        if str(expected).lower() != actual:
            issues.append(
                _issue(
                    ERROR,
                    "checksums.mismatch",
                    f"SHA256 mismatch for {rel}: expected {expected}, got {actual}.",
                    target,
                )
            )


def _validate_run_config(root: Path, issues: list[Issue]) -> None:
    run, issue = _load_yaml(root / "config" / "run.yaml")
    if issue is not None:
        issues.append(issue)
        return
    assert run is not None
    mu = run.get("management_unit")
    if not isinstance(mu, dict) or not mu.get("id"):
        issues.append(
            _issue(
                ERROR,
                "run.management_unit",
                "management_unit.id is required (one instance = one management unit).",
                root / "config" / "run.yaml",
            )
        )
    for key in ("horizon_years", "utilization"):
        if key not in run:
            issues.append(
                _issue(
                    ERROR,
                    "run.missing_key",
                    f"run.yaml is missing '{key}'.",
                    root / "config" / "run.yaml",
                )
            )
    even_flow = run.get("even_flow")
    if not isinstance(even_flow, dict) or "epsilon" not in even_flow:
        issues.append(
            _issue(
                ERROR,
                "run.even_flow",
                "even_flow.epsilon is required.",
                root / "config" / "run.yaml",
            )
        )
    scenarios = run.get("scenarios")
    if not isinstance(scenarios, dict) or not isinstance(scenarios.get("epsilon_steps"), int):
        issues.append(
            _issue(
                ERROR,
                "run.scenarios",
                "scenarios.epsilon_steps (integer) is required.",
                root / "config" / "run.yaml",
            )
        )


def _validate_species_and_coefficients(root: Path, issues: list[Issue]) -> None:
    species_cfg, issue = _load_yaml(root / "config" / "species.yaml")
    if issue is not None:
        issues.append(issue)
        return
    coefficients, issue = _load_yaml(root / "bird" / "coefficients.yaml")
    if issue is not None:
        issues.append(issue)
        return
    assert species_cfg is not None and coefficients is not None

    entries = species_cfg.get("species")
    if not isinstance(entries, list) or not entries:
        issues.append(
            _issue(
                ERROR,
                "species.empty",
                "species.yaml must define a non-empty species list.",
                root / "config" / "species.yaml",
            )
        )
        return
    codes = set()
    guilds = set(species_cfg.get("guilds") or [])
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("code"):
            issues.append(
                _issue(
                    ERROR,
                    "species.entry",
                    f"Species entry missing 'code': {entry!r}",
                    root / "config" / "species.yaml",
                )
            )
            continue
        code = str(entry["code"])
        codes.add(code)
        snapshot = TAXONOMY_SNAPSHOT.get(code)
        if snapshot is None:
            issues.append(
                _issue(
                    ERROR,
                    "species.unknown_code",
                    f"Species code '{code}' is not in the eBird taxonomy snapshot.",
                    root / "config" / "species.yaml",
                )
            )
        elif entry.get("common") and str(entry["common"]).lower() != snapshot["common"].lower():
            issues.append(
                _issue(
                    WARNING,
                    "species.common_mismatch",
                    f"Common name '{entry['common']}' does not match taxonomy "
                    f"'{snapshot['common']}' for code '{code}'.",
                    root / "config" / "species.yaml",
                )
            )
        guild = entry.get("guild")
        if guild and guilds and guild not in guilds:
            issues.append(
                _issue(
                    WARNING,
                    "species.guild_unknown",
                    f"Species '{entry['code']}' references undeclared guild '{guild}'.",
                    root / "config" / "species.yaml",
                )
            )
    if not isinstance(coefficients.get("source"), dict):
        issues.append(
            _issue(
                WARNING,
                "coefficients.source",
                "coefficients.yaml should carry a provenance 'source' mapping.",
                root / "bird" / "coefficients.yaml",
            )
        )
    coeff_species = coefficients.get("species")
    if not isinstance(coeff_species, dict) or not coeff_species:
        issues.append(
            _issue(
                ERROR,
                "coefficients.empty",
                "coefficients.yaml must define a non-empty species mapping.",
                root / "bird" / "coefficients.yaml",
            )
        )
        return
    coeff_codes = set(coeff_species.keys())
    for missing in sorted(codes - coeff_codes):
        issues.append(
            _issue(
                ERROR,
                "coefficients.missing_species",
                f"Configured species '{missing}' has no fitted coefficients.",
                root / "bird" / "coefficients.yaml",
            )
        )
    for extra in sorted(coeff_codes - codes):
        issues.append(
            _issue(
                WARNING,
                "coefficients.extra_species",
                f"Coefficients exist for '{extra}' but it is not configured.",
                root / "bird" / "coefficients.yaml",
            )
        )


def _validate_layout(root: Path, issues: list[Issue]) -> None:
    inputs = root / "inputs"
    if not inputs.is_dir():
        issues.append(_issue(WARNING, "inputs.missing", "inputs/ directory is missing.", inputs))
    elif not any(inputs.iterdir()):
        issues.append(_issue(WARNING, "inputs.empty", "inputs/ directory is empty.", inputs))
    results = root / "results"
    if not results.is_dir():
        issues.append(
            _issue(
                WARNING,
                "results.missing",
                "results/ missing (engine creates it at run time).",
                results,
            )
        )
    for path in root.rglob("*"):
        if path.is_file() and _looks_like_raw_ebird(path.name):
            issues.append(
                _issue(
                    ERROR,
                    "boundary.raw_ebird",
                    "Raw eBird files must not be stored inside instances (see eBird Terms of Use).",
                    path,
                )
            )


def validate_instance(root: Path | str) -> list[Issue]:
    """Validate an instance directory against the data contract.

    Returns a list of issues (empty = clean). Errors block use; warnings are
    advisory.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return [_issue(ERROR, "root.missing", "Instance root is not a directory.", root_path)]

    issues: list[Issue] = []
    _validate_manifest(root_path, issues)
    _validate_run_config(root_path, issues)
    _validate_species_and_coefficients(root_path, issues)
    _validate_layout(root_path, issues)
    return issues
