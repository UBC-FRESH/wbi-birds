from __future__ import annotations

import shutil
from pathlib import Path

from wbi_birds.instance import ERROR, validate_instance

FIXTURE = Path(__file__).parent / "fixtures" / "instance_valid"


def _errors(issues) -> list:
    return [issue for issue in issues if issue.severity == ERROR]


def _codes(issues) -> set[str]:
    return {issue.code for issue in issues}


def _copy_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "instance_valid"
    shutil.copytree(FIXTURE, root)
    return root


SPECIES = (
    "rebnut",
    "borchi2",
    "gockin",
    "brncre",
    "yerwar",
    "swathr",
    "whtspa",
    "tenwar",
    "yebsap",
)


def _write_response_table(root: Path, species=SPECIES) -> None:
    lines = ["species_code,development_type,age,bird_value,bird_value_sd"]
    for code in species:
        lines.append(f'{code},"tsa24_clipped|0|AU|1|AU",80,0.5,0.1')
    (root / "bird" / "response_table.csv").write_text("\n".join(lines) + "\n")
    (root / "bird" / "coefficients.yaml").unlink()


def test_valid_fixture_has_no_errors() -> None:
    issues = validate_instance(FIXTURE)
    assert _errors(issues) == [], [
        issue.to_dict() if hasattr(issue, "to_dict") else issue for issue in issues
    ]


def test_missing_manifest(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    (root / "manifest.yaml").unlink()
    assert "file.missing" in _codes(validate_instance(root))


def test_species_without_bird_data(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    species = root / "config" / "species.yaml"
    species.write_text(
        species.read_text().replace(
            "guilds: [",
            "  - {code: nope1, common: Nope, guild: mature_conifer}\nguilds: [",
        )
    )
    assert "bird.missing_species" in _codes(validate_instance(root))


def test_response_table_only_instance_valid(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    _write_response_table(root)
    assert _errors(validate_instance(root)) == []


def test_response_table_invalid(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    _write_response_table(root)
    bad = root / "bird" / "response_table.csv"
    bad.write_text("species_code,development_type,age\nrebnut,dt|0,80\n")
    assert "response_table.invalid" in _codes(validate_instance(root))


def test_response_table_missing_species(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    _write_response_table(root, species=SPECIES[:-1])
    codes = _codes(validate_instance(root))
    assert "bird.missing_species" in codes


def test_raw_ebird_file_rejected(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    raw = root / "inputs" / "ebd_CA-BC_rebnut_relAug-2019.zip"
    raw.write_text("not-really-a-zip")
    assert "boundary.raw_ebird" in _codes(validate_instance(root))


def test_checksum_mismatch(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    manifest = root / "manifest.yaml"
    manifest.write_text(
        manifest.read_text().replace(
            "files: {}",
            f'files:\n    inputs/README.md: "{"0" * 64}"',
        )
    )
    assert "checksums.mismatch" in _codes(validate_instance(root))


def test_missing_root(tmp_path: Path) -> None:
    assert _codes(validate_instance(tmp_path / "nope")) == {"root.missing"}
