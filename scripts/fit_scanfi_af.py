"""Fit nine species on year-matched SCANFI 240 m neighbourhood metrics.

Base: log1p(softwood), log1p(hardwood), age projected to the observation year.
Spatial: forest, edge and early-seral fractions in an 8-cell (1.92 km) window.
Fit window: 2018-2026, paired with SCANFI 2020 (2018-2022) or 2025 (2023+).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from wbi_birds.regression import aggregate_wood_types, correct_stand_age, fit_poisson_glm

ROOT = Path("/srv/shared-data/gep/wbi-birds")
SAMPLES = ROOT / "campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz"
METRICS = ROOT / "fvsbc-work/scanfi-240m/checklist-metrics.npz"
ZEROFILL = ROOT / "campaigns/ws4-five-tsa-2026-11/suite-zero-fill/ebd_suite_zero_filled.csv"
OUT = ROOT / "campaigns/ws4-five-tsa-2026-11/bird-fits/scanfi-240m-nine-species-spatial.json"

SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
SOFTWOOD = ("Pice_Eng", "Pice_Gla", "Pice_Mar", "Pinu_Con", "Pseu_Men", "Abie_Las",
            "Pinu_Mon", "Tsug_Mer", "Lari_Lya", "Pinu_Alb", "Pice_Spp", "Abie_Ama",
            "Lari_Lar", "Tsug_Het", "Abie_Bal", "Thuj_Pli")
HARDWOOD = ("Popu_Tre", "Popu_Spp", "Sali_Spp", "Popu_Tri", "Betu_Pap")
BASE_TERMS = ("log1p_softwood", "log1p_hardwood", "age")
SPATIAL_TERMS = ("pct_forest_1km", "edge_1km", "pct_early_500m")


def main() -> int:
    sample = np.load(SAMPLES, allow_pickle=False)
    metrics = np.load(METRICS, allow_pickle=False)
    assert np.array_equal(sample["checklist_id"].astype(str), metrics["checklist_id"].astype(str))
    year = sample["year"].astype(int)
    samples = {n: sample[n].astype(np.float64) for n in (*SOFTWOOD, *HARDWOOD, "mvol", "age")}
    idx_l, sw_l, hw_l, age_l = [], [], [], []
    for i in range(len(year)):
        species = {n: samples[n][i] for n in (*SOFTWOOD, *HARDWOOD)
                   if np.isfinite(samples[n][i])}
        sw_i, hw_i = aggregate_wood_types(
            species, softwood_species=SOFTWOOD, hardwood_species=HARDWOOD,
            merchantable_volume=samples["mvol"][i], factor=0.01)
        a = correct_stand_age(float(samples["age"][i]), int(year[i]))
        if a is None:
            continue
        idx_l.append(i); sw_l.append(sw_i); hw_l.append(hw_i); age_l.append(a)
    idx = np.asarray(idx_l, dtype=np.int64)
    sw = np.asarray(sw_l); hw = np.asarray(hw_l); age = np.asarray(age_l)
    z = np.column_stack([
        metrics["pct_forest_2km"][idx].astype(float),
        metrics["edge_2km"][idx].astype(float),
        metrics["pct_early_2km"][idx].astype(float),
    ])
    keep = (year[idx] >= 2018) & np.isfinite(z).all(axis=1) & np.isfinite(age) & (age >= 0)
    idx, sw, hw, age, z = idx[keep], sw[keep], hw[keep], age[keep], z[keep]
    print(f"fit rows {len(idx):,} (2018-2026, complete SCANFI metrics)")

    xbase = np.column_stack([np.log1p(sw), np.log1p(hw), age])
    checklist = sample["checklist_id"].astype(str)
    zf = pd.read_csv(ZEROFILL, usecols=["checklist_id", "species_code", "observation_count"],
                     dtype={"checklist_id": str})
    pos = pd.Series(np.arange(len(checklist)), index=checklist)
    zf["pos"] = zf["checklist_id"].map(pos)
    zf = zf.dropna(subset=["pos"])

    out = {
        "covariate_form": "log1p",
        "definition": "volume_allocated",
        "link": "log (Poisson GLM)",
        "spatial_form": "local",
        "spatial_terms": list(SPATIAL_TERMS),
        "spatial_scale_m": 1920,
        "source": "SCANFI v2 age_median + att_biomass, 30 m aggregated to 240 m (8x8), 8-cell window",
        "fit_years": "2018-2026",
        "year_pairing": "2018-2022 -> SCANFI 2020; 2023+ -> SCANFI 2025",
        "species": {},
    }
    print(f"{'species':9s} {'AIC_base':>12s} {'AIC_spat':>12s} {'dAIC':>10s} {'disp':>7s}")
    for species in SPECIES:
        group = zf[zf["species_code"] == species]
        counts = np.zeros(len(checklist), dtype=float)
        counts[group["pos"].to_numpy(dtype=np.int64)] = np.nan_to_num(
            group["observation_count"].to_numpy(dtype=float), nan=0.0)
        y = counts[idx]
        base = fit_poisson_glm(xbase, y, BASE_TERMS)
        xfull = np.column_stack([xbase, z])
        full = fit_poisson_glm(xfull, y, (*BASE_TERMS, *SPATIAL_TERMS))
        names = ("intercept", *BASE_TERMS, *SPATIAL_TERMS)
        eta = np.column_stack([np.ones(len(y)), xfull]) @ np.array([full.coefficients[n] for n in names])
        eta_cap = float(np.percentile(eta, 99.9))
        out["species"][species] = {
            "n": int(len(y)),
            "aic": float(full.aic),
            "aic_base": float(base.aic),
            "delta_aic": float(full.aic - base.aic),
            "dispersion": float(full.dispersion),
            "eta_cap": eta_cap,
            "coefficients": {k: float(v) for k, v in full.coefficients.items()},
            "std_errors": {k: float(v) for k, v in full.std_errors.items()},
        }
        print(f"{species:9s} {base.aic:12.0f} {full.aic:12.0f} {full.aic-base.aic:10.0f} "
              f"{full.dispersion:7.2f}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
