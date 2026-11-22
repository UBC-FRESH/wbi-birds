#!/usr/bin/env python
"""Zero-fill the nine-species BC breeding suite from the private EBD/SED extracts.

Derived product only; observer identifiers are never written. The output is a
checklist x species grid with detections, non-detections and censored X counts.
"""
from pathlib import Path
import json

from wbi_birds.ingest import ZeroFillSpec, ingest_ebd_zero_filled

DERIVED = Path("/srv/shared-data/gep/wbi-birds/wbi-ebird-data/derived/world-2026-09")
OUT = Path("/srv/shared-data/gep/wbi-birds/campaigns/rbnu-contract-full/TSA24/instance/bird/derived")
OUT.mkdir(parents=True, exist_ok=True)

SPECIES = (
    "rebnut",   # Red-breasted Nuthatch
    "borchi2",  # Boreal Chickadee
    "gockin",   # Golden-crowned Kinglet
    "brncre",   # Brown Creeper
    "yerwar",   # Yellow-rumped Warbler
    "swathr",   # Swainson's Thrush
    "whtspa",   # White-throated Sparrow
    "tenwar",   # Tennessee Warbler
    "yebsap",   # Yellow-bellied Sapsucker
)

spec = ZeroFillSpec(
    ebd_path=DERIVED / "ebd_bc_suite_breeding.tsv",
    sed_path=DERIVED / "sed_bc_breeding.tsv",
    out_csv=OUT / "ebd_suite_zero_filled.csv",
    species=SPECIES,
    months=(5, 6, 7, 8),
    complete_checklists_only=True,
)

summary = ingest_ebd_zero_filled(spec)
sidecar = spec.out_csv.with_name(spec.out_csv.name + ".provenance.json")
sidecar.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
