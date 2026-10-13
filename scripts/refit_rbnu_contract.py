"""Re-estimate the RBNU response under the volume-allocation unit contract (E-P4.11).

Inputs (private store, ``external/wbi-ebird-data``):

- ``raw/ebd/ebd_CA-BC_rebnut_relAug-2019.zip`` — the as-received EBD archive;
- ``derived/rbnu-legacy/rbnu_legacy_samples.npz`` — per-point kNN v1 samples
  (21 treeSp species biomass, merchantable volume, stand age, year, count) for
  the 65,373 breeding-season rows, in EBD file order;
- ``derived/rbnu-legacy/study_area/bc_tsa_study_area.geojson.gz`` — the 41-TSA
  study area used by the 2019 run.

The script (1) rebuilds the TSA mask from the EBD coordinates, (2) assembles
covariate rows with :func:`wbi_birds.covariates.build_covariate_rows`, (3) fits
the native Poisson GLM under the accepted contract ``volume_allocated``, and
(4) fits the 2019 ``legacy_biomass_scaled`` definition on the same rows as a
parity check. The parity fit must reproduce the validated 2019 reconstruction
(n = 63,135; coefficients within 1e-9 of ``rbnu_legacy_fit.json``); if it does
not, the script exits non-zero and writes nothing.

Usage::

    python scripts/refit_rbnu_contract.py --store <private-store-root>
        [--out results/bird/rbnu_contract_fit.json]

The store is the private DataLad clone; the engine submodule must be ``datalad get``-materialised
first. The output records the engine version and ``git describe`` output, the Poisson and
quasi-Poisson standard errors, and two sensitivity fits: without zero-volume rows, and without
the age term.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.path import Path as PolygonPath
from rasterio.warp import transform as warp_transform

from wbi_birds import __version__
from wbi_birds.covariates import build_covariate_rows
from wbi_birds.ingest import _open_text_member
from wbi_birds.regression import fit_poisson_glm, quasi_poisson_summary

REPO_ROOT = Path(__file__).resolve().parents[1]
SOFTWOOD = (
    "Pice_Eng",
    "Pice_Gla",
    "Pice_Mar",
    "Pinu_Con",
    "Pseu_Men",
    "Abie_Las",
    "Pinu_Mon",
    "Tsug_Mer",
    "Lari_Lya",
    "Pinu_Alb",
    "Pice_Spp",
    "Abie_Ama",
    "Lari_Lar",
    "Tsug_Het",
    "Abie_Bal",
    "Thuj_Pli",
)
HARDWOOD = ("Popu_Tre", "Popu_Spp", "Sali_Spp", "Popu_Tri", "Betu_Pap")
PARITY_ABS_TOL = 1e-9
EXPECTED_ROWS = 65373  # breeding-season rows in the EBD (validated 2026-10-12)
LEGACY_N = 63135  # 2019 fit / TSA-masked reconstruction


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_describe() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "describe", "--always", "--dirty", "--abbrev=7"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out or "unknown"


def _breeding_points(zip_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Longitude, latitude, year and count for months 5-8, in EBD file order."""
    with _open_text_member(zip_path, "ebd_") as (handle, _member):
        frame = pd.read_csv(
            handle,
            sep="\t",
            usecols=["OBSERVATION COUNT", "LATITUDE", "LONGITUDE", "OBSERVATION DATE"],
            dtype=str,
        )
    dates = pd.to_datetime(frame["OBSERVATION DATE"], errors="coerce")
    keep = dates.dt.month.isin([5, 6, 7, 8]).to_numpy()
    frame = frame[keep]
    count = pd.to_numeric(frame["OBSERVATION COUNT"].replace("X", "0"), errors="coerce").to_numpy()
    lon = frame["LONGITUDE"].astype(float).to_numpy()
    lat = frame["LATITUDE"].astype(float).to_numpy()
    year = dates[keep].dt.year.to_numpy()
    return lon, lat, year, count


def _tsa_mask(geojson_gz: Path, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    xs, ys = warp_transform("EPSG:4326", "EPSG:3005", lon.tolist(), lat.tolist())
    points = np.column_stack([np.asarray(xs), np.asarray(ys)])
    with gzip.open(geojson_gz, "rt", encoding="utf-8") as handle:
        collection = json.load(handle)
    inside = np.zeros(len(points), dtype=bool)
    for feature in collection["features"]:
        geometry = feature["geometry"]
        if geometry["type"] == "Polygon":
            rings = [geometry["coordinates"][0]]
        else:
            rings = [polygon[0] for polygon in geometry["coordinates"]]
        for ring in rings:
            inside |= PolygonPath(np.asarray(ring)).contains_points(points, radius=0.0)
    return inside


def _fit_block(
    rows: list[dict[str, float]], terms: tuple[str, ...] = ("softwood", "hardwood", "age")
) -> dict[str, object]:
    design = np.array([[row[term] for term in terms] for row in rows], dtype=float)
    counts = np.array([row["observation_count"] for row in rows], dtype=float)
    result = fit_poisson_glm(design, counts, terms)
    return {
        "quasi_poisson": quasi_poisson_summary(result),
        "n": result.n,
        "coefficients": result.coefficients,
        "std_errors": result.std_errors,
        "z_values": result.z_values,
        "p_values": result.p_values,
        "null_deviance": result.null_deviance,
        "residual_deviance": result.residual_deviance,
        "aic": result.aic,
        "dispersion": result.dispersion,
        "converged": result.converged,
    }


def _drop_accounting(arrays: dict[str, np.ndarray], names: tuple[str, ...]) -> dict[str, int]:
    """Explain every row removed from the TSA-masked study area, one reason per row.

    Order matters and mirrors ``build_covariate_rows``: missing classified biomass or
    volume first, then positive volume with zero classified biomass, then negative
    projected age.
    """
    species = np.column_stack([arrays[name] for name in (*SOFTWOOD, *HARDWOOD)])
    mvol = arrays["mvol"]
    missing = np.isnan(species).any(axis=1) | np.isnan(mvol)
    biomass = np.nansum(species, axis=1)
    zero_share = ~missing & (mvol > 0) & (biomass <= 0)
    projected = arrays["age"] - (2011 - arrays["year"])
    age_negative = ~missing & ~zero_share & (projected < 0)
    kept = ~missing & ~zero_share & ~age_negative
    return {
        "study_area": len(mvol),
        "missing_biomass_or_volume": int(missing.sum()),
        "positive_volume_zero_biomass": int(zero_share.sum()),
        "negative_projected_age": int(age_negative.sum()),
        "zero_volume_kept_at_zero_wood_volume": int(((mvol == 0) & kept).sum()),
        "retained": int(kept.sum()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=REPO_ROOT / "external" / "wbi-ebird-data")
    parser.add_argument(
        "--out", type=Path, default=REPO_ROOT / "results" / "bird" / "rbnu_contract_fit.json"
    )
    args = parser.parse_args(argv)

    store = args.store
    zip_path = store / "raw" / "ebd" / "ebd_CA-BC_rebnut_relAug-2019.zip"
    samples_path = store / "derived" / "rbnu-legacy" / "rbnu_legacy_samples.npz"
    study_area = store / "derived" / "rbnu-legacy" / "study_area" / "bc_tsa_study_area.geojson.gz"
    fit_reference = store / "derived" / "rbnu-legacy" / "rbnu_legacy_fit.json"
    for required in (zip_path, samples_path, study_area, fit_reference):
        if not required.is_file() or required.stat().st_size == 0:
            print(f"missing or empty private input (run `datalad get` in the store): {required}")
            return 2

    lon, lat, year_ebd, count_ebd = _breeding_points(zip_path)
    samples = np.load(samples_path)
    if len(samples["year"]) != EXPECTED_ROWS or len(lon) != EXPECTED_ROWS:
        print(
            f"row mismatch: samples={len(samples['year'])} ebd={len(lon)} expected={EXPECTED_ROWS}"
        )
        return 1
    if not np.array_equal(samples["year"], year_ebd) or not np.array_equal(
        samples["count"], count_ebd, equal_nan=True
    ):
        print("sample rows are not aligned with the EBD breeding-season rows; refusing to refit")
        return 1

    inside = _tsa_mask(study_area, lon, lat)
    arrays = {name: samples[name][inside] for name in samples.files}
    names = (*SOFTWOOD, *HARDWOOD, "mvol", "age")
    columns = {name: arrays[name] for name in names}

    def assemble(definition: str) -> list[dict[str, float]]:
        return build_covariate_rows(
            columns,
            softwood_species=SOFTWOOD,
            hardwood_species=HARDWOOD,
            merchantable_volume="mvol",
            knn_age="age",
            observation_year=arrays["year"],
            definition=definition,
            response=arrays["count"],
        )

    drop_accounting = _drop_accounting(arrays, names)
    contract_rows = assemble("volume_allocated")
    parity_rows = assemble("legacy_biomass_scaled")
    contract = _fit_block(contract_rows)
    parity = _fit_block(parity_rows)
    zero_volume_free = [
        row for row in contract_rows if row["softwood"] != 0.0 or row["hardwood"] != 0.0
    ]
    sensitivities = {
        "no_zero_volume_rows": _fit_block(zero_volume_free),
        "no_age_term": _fit_block(contract_rows, terms=("softwood", "hardwood")),
    }

    reference = json.loads(fit_reference.read_text(encoding="utf-8"))["native_python_tsa_masked"]
    parity_gap = max(
        abs(parity["coefficients"][term] - reference["coefficients"][term])
        for term in ("intercept", "softwood", "hardwood", "age")
    )
    if parity["n"] != LEGACY_N or parity_gap > PARITY_ABS_TOL:
        print(
            "PARITY FAILED: legacy definition n={} (expected {}), max coefficient gap {:.3e} "
            "(tolerance {:.0e}); not writing results.".format(
                parity["n"], LEGACY_N, parity_gap, PARITY_ABS_TOL
            )
        )
        return 1

    # The invariant is checked against each fitted row's own merchantable volume.
    kept = np.array([row["source_index"] for row in contract_rows], dtype=int)
    fitted_wood = np.array(
        [row["softwood"] + row["hardwood"] for row in contract_rows], dtype=float
    )
    invariant_gap = float(np.max(np.abs(fitted_wood - arrays["mvol"][kept]))) if len(kept) else 0.0

    payload = {
        "definition": "volume_allocated",
        "unit_contract": "planning/unit-contract-decision.md (GP working default, Option 1)",
        "denominator": "sum of the 21 classified treeSp species biomass",
        "state_vector": ["softwood", "hardwood", "age"],
        "units": {"softwood": "m3/ha", "hardwood": "m3/ha", "age": "years"},
        "link": "log (Poisson GLM); bird value per state = exp(eta)",
        "study_area": "BC_TSA_corrected (41 TSAs), points inside the union",
        "months": [5, 6, 7, 8],
        "rows_in_study_area": int(inside.sum()),
        "rows_fitted": contract["n"],
        "rows_dropped": drop_accounting,
        "invariant_max_abs_gap_softwood_plus_hardwood_minus_mvol": invariant_gap,
        "fit": {key: value for key, value in contract.items() if key not in ("n", "quasi_poisson")},
        "quasi_poisson": {
            "basis": "dispersion = residual deviance / residual df; SE x sqrt(dispersion)",
            **contract["quasi_poisson"],
        },
        "sensitivities": sensitivities,
        "parity_legacy_definition": {
            "n": parity["n"],
            "max_coefficient_gap_vs_2019_reconstruction": parity_gap,
            "tolerance": PARITY_ABS_TOL,
            "passed": True,
        },
        "provenance": {
            "wbi_birds_version": __version__,
            "wbi_birds_commit": _git_describe(),
            "ebd_zip_sha256": _sha256(zip_path),
            "samples_npz_sha256": _sha256(samples_path),
            "study_area_geojson_gz_sha256": _sha256(study_area),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=float) + "\n", encoding="utf-8"
    )

    print(f"parity (legacy definition): n={parity['n']} max coefficient gap={parity_gap:.2e}  PASS")
    accounting = payload["rows_dropped"]
    print(
        "contract (volume_allocated): retained n={} of {} study-area rows".format(
            contract["n"], accounting["study_area"]
        )
    )
    print(
        "  dropped: missing={} positive-volume-zero-biomass={} negative-age={}; "
        "zero-volume rows kept at zero wood volume={}".format(
            accounting["missing_biomass_or_volume"],
            accounting["positive_volume_zero_biomass"],
            accounting["negative_projected_age"],
            accounting["zero_volume_kept_at_zero_wood_volume"],
        )
    )
    for term in ("intercept", "softwood", "hardwood", "age"):
        print(
            f"  {term:10s} {contract['coefficients'][term]: .6e}  "
            f"se {contract['std_errors'][term]:.3e}  "
            f"legacy {parity['coefficients'][term]: .6e}"
        )
    print(f"  invariant max gap (sw+hw-mvol): {invariant_gap:.2e}")
    for term in ("intercept", "softwood", "hardwood", "age"):
        print(f"  quasi-Poisson se {term:10s} {contract['quasi_poisson']['std_errors'][term]:.3e}")
    for name, block in sensitivities.items():
        coefs = ", ".join(f"{term}={value: .4e}" for term, value in block["coefficients"].items())
        print(f"sensitivity {name}: n={block['n']} {coefs}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
