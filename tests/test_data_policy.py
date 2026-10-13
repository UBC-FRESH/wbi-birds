"""Guard against committing real-format eBird identifiers (see AGENTS.md, Data handling).

Example and test fixtures must use synthetic placeholders. This scan covers every git-tracked
file. Failure messages list locations only: CI logs are public, so matched values are never
printed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
THIS_FILE = "tests/test_data_policy.py"
BINARY_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".tif", ".tiff", ".ico", ".gz", ".npz", ".pkl"}
    | {".xlsx", ".parquet", ".feather"}
)
ARCHIVE_SUFFIXES = frozenset({".zip"})
IDENTIFIER_PATTERNS = {
    "observer identifier": re.compile(r"\bobsr\d{4,}\b", re.IGNORECASE),
    "eBird global unique identifier": re.compile(
        r"URN:CornellLabOfOrnithology:EBIRD", re.IGNORECASE
    ),
    "eBird checklist identifier": re.compile(r"\bS\d{8,10}\b"),
}


def _tracked_files() -> list[Path]:
    try:
        listing = subprocess.run(
            ["git", "-C", str(REPO), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout; tracked-file scan skipped")
    return [REPO / rel for rel in listing if rel != THIS_FILE and (REPO / rel).is_file()]


def test_no_real_format_ebird_identifiers_in_tracked_files() -> None:
    findings: list[str] = []
    for path in _tracked_files():
        if path.suffix.lower() in BINARY_SUFFIXES | ARCHIVE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            findings.extend(
                f"{path.relative_to(REPO)}:{lineno} ({label})"
                for label, pattern in IDENTIFIER_PATTERNS.items()
                if pattern.search(line)
            )
    assert not findings, (
        "Real-format eBird identifiers found. Replace them with placeholders "
        "(obsrSYN##, S### checklist IDs):\n" + "\n".join(findings)
    )


def test_no_archives_tracked() -> None:
    archives = [
        str(path.relative_to(REPO))
        for path in _tracked_files()
        if path.suffix.lower() in ARCHIVE_SUFFIXES
    ]
    assert not archives, (
        f"Archives must not be tracked; raw data stays in the private store: {archives}"
    )
