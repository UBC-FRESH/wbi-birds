"""Fit the spatial anticipation functions and compare to the aspatial log form.

Base (aspatial log): log1p(sw), log1p(hw), age
Spatial adds:        pct_forest_1km, edge_1km, pct_early_500m,
                     log1p(mature_patch_ha), log1p(dist_mature_m + 1)

    python scripts/fit_spatial_af.py --sample <npz> --spatial <npz> --zerofill <csv> --out <json>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from wbi_birds.covariates import build_covariate_rows
from wbi_birds.regression import fit_poisson_glm

SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
SOFTWOOD = (
    "Pice_Eng", "Pice_Gla", "Pice_Mar", "Pinu_Con", "Pseu_Men", "Abie_Las",
    "Pinu_Mon", "Tsug_Mer", "Lari_Lya", "Pinu_Alb", "Pice_Spp", "Abie_Ama",
    "Lari_Lar", "Tsug_Het", "Abie_Bal", "Thuj_Pli",
)
HARDWOOD = ("Popu_Tre", "Popu_Spp", "Sali_Spp", "Popu_Tri", "Betu_Pap")
BASE_TERMS = ("log1p_softwood", "log1p_hardwood", "age")
SPATIAL_TERMS = ("pct_forest_1km", "edge_1km", "pct_early_500m",
                 "log1p_patch_ha", "log1p_dist_mature_m")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--spatial", type=Path, required=True)
    parser.add_argument("--zerofill", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sample = np.load(args.sample, allow_pickle=False)
    spatial = np.load(args.spatial, allow_pickle=False)
    checklist = sample["checklist_id"].astype(str)
    samples = {n: sample[n].astype(np.float64) for n in (*SOFTWOOD, *HARDWOOD, "mvol", "age")}
    rows = build_covariate_rows(
        samples, softwood_species=SOFTWOOD, hardwood_species=HARDWOOD,
        merchantable_volume="mvol", knn_age="age",
        observation_year=sample["year"], definition="volume_allocated",
    )
    idx = np.array([r["source_index"] for r in rows], dtype=np.int64)
    sw = np.array([r["softwood"] for r in rows])
    hw = np.array([r["hardwood"] for r in rows])
    age = np.array([r["age"] for r in rows])
    print(f"rows {len(rows):,}")

    xbase = np.column_stack([np.log1p(sw), np.log1p(hw), age])
    z = np.column_stack([
        spatial["pct_forest_1km"][idx].astype(float),
        spatial["edge_1km"][idx].astype(float),
        spatial["pct_early_500m"][idx].astype(float),
        np.log1p(spatial["mature_patch_ha"][idx].astype(float)),
        np.log1p(spatial["dist_mature_m"][idx].astype(float)),
    ])
    okay = np.isfinite(z).all(axis=1)
    xbase, z, idx2 = xbase[okay], z[okay], idx[okay]
    print(f"complete spatial rows {len(xbase):,}")

    zf = pd.read_csv(args.zerofill, usecols=["checklist_id", "species_code", "observation_count"],
                     dtype={"checklist_id": str})
    pos = pd.Series(np.arange(len(checklist)), index=checklist)
    zf["pos"] = zf["checklist_id"].map(pos)
    zf = zf.dropna(subset=["pos"])

    out = {"base_terms": list(BASE_TERMS), "spatial_terms": list(SPATIAL_TERMS),
           "corr": {}, "species": {}}
    for i, name in enumerate(SPATIAL_TERMS):
        out["corr"][name] = {
            "log1p_softwood": round(float(np.corrcoef(z[:, i], xbase[:, 0])[0, 1]), 3),
            "log1p_hardwood": round(float(np.corrcoef(z[:, i], xbase[:, 1])[0, 1]), 3),
            "age": round(float(np.corrcoef(z[:, i], xbase[:, 2])[0, 1]), 3),
        }

    print(f"{'species':9s} {'AIC_base':>10s} {'AIC_spat':>10s} {'dAIC':>8s} {'disp_s':>7s}")
    for species in SPECIES:
        group = zf[zf["species_code"] == species]
        counts = np.zeros(len(checklist), dtype=float)
        counts[group["pos"].to_numpy(dtype=np.int64)] = np.nan_to_num(
            group["observation_count"].to_numpy(dtype=float), nan=0.0)
        y = counts[idx2]
        base = fit_poisson_glm(xbase, y, BASE_TERMS)
        full = fit_poisson_glm(np.column_stack([xbase, z]), y, (*BASE_TERMS, *SPATIAL_TERMS))
        out["species"][species] = {
            "n": int(len(y)),
            "aic_base": float(base.aic),
            "aic_spatial": float(full.aic),
            "delta_aic": float(full.aic - base.aic),
            "dispersion_spatial": float(full.dispersion),
            "coefficients": {k: float(v) for k, v in full.coefficients.items()},
        }
        print(f"{species:9s} {base.aic:10.0f} {full.aic:10.0f} {full.aic-base.aic:8.0f} "
              f"{full.dispersion:7.2f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
