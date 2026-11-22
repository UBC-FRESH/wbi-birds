"""Compare anticipation-function forms on the same checklist sample.

Forms:
  linear     log(mu) = b0 + b1*sw + b2*hw + b3*age
  log        log(mu) = b0 + b1*log1p(sw) + b2*log1p(hw) + b3*age
  log_age2   log(mu) = b0 + b1*log1p(sw) + b2*log1p(hw) + b3*age + b4*age^2

Reports AIC, quasi-Poisson dispersion, and the predicted count at the 99.9th
percentile of each covariate (the extrapolation stress test).

    python scripts/fit_af_forms.py --sample <npz> --zerofill <csv> --out <json>
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


def forms(sw: np.ndarray, hw: np.ndarray, age: np.ndarray) -> dict[str, tuple[np.ndarray, list[str]]]:
    return {
        "linear": (np.column_stack([sw, hw, age]), ["softwood", "hardwood", "age"]),
        "log": (np.column_stack([np.log1p(sw), np.log1p(hw), age]),
                ["log1p_softwood", "log1p_hardwood", "age"]),
        "log_age2": (np.column_stack([np.log1p(sw), np.log1p(hw), age, age**2]),
                     ["log1p_softwood", "log1p_hardwood", "age", "age2"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--zerofill", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sample = np.load(args.sample, allow_pickle=False)
    checklist = sample["checklist_id"].astype(str)
    samples = {n: sample[n].astype(np.float64) for n in (*SOFTWOOD, *HARDWOOD, "mvol", "age")}
    rows = build_covariate_rows(
        samples,
        softwood_species=SOFTWOOD,
        hardwood_species=HARDWOOD,
        merchantable_volume="mvol",
        knn_age="age",
        observation_year=sample["year"],
        definition="volume_allocated",
    )
    idx = np.array([r["source_index"] for r in rows], dtype=np.int64)
    sw = np.array([r["softwood"] for r in rows])
    hw = np.array([r["hardwood"] for r in rows])
    age = np.array([r["age"] for r in rows])
    print(f"rows {len(rows):,}")

    zf = pd.read_csv(args.zerofill, usecols=["checklist_id", "species_code", "observation_count"],
                     dtype={"checklist_id": str})
    pos = pd.Series(np.arange(len(checklist)), index=checklist)
    zf["pos"] = zf["checklist_id"].map(pos)
    zf = zf.dropna(subset=["pos"])

    p999 = {name: float(np.percentile(values, 99.9)) for name, values in
            (("softwood", sw), ("hardwood", hw), ("age", age))}
    stress = np.column_stack([
        np.array([p999["softwood"]]), np.array([p999["hardwood"]]), np.array([p999["age"]])
    ])
    stress_log = np.column_stack([np.log1p(stress[:, 0]), np.log1p(stress[:, 1]), stress[:, 2]])
    stress_log2 = np.column_stack([stress_log, stress[:, 2] ** 2])

    out = {"rows": len(rows), "p999": p999, "species": {}}
    print(f"{'species':9s} {'AIC_lin':>10s} {'AIC_log':>10s} {'AIC_log2':>9s} "
          f"{'disp_lin':>8s} {'disp_log':>8s} {'pred999_lin':>11s} {'pred999_log':>11s} {'obsmax':>7s}")
    for species in SPECIES:
        group = zf[zf["species_code"] == species]
        counts = np.zeros(len(checklist), dtype=float)
        counts[group["pos"].to_numpy(dtype=np.int64)] = np.nan_to_num(
            group["observation_count"].to_numpy(dtype=float), nan=0.0
        )
        y = counts[idx]
        entry = {"obs_max": int(y.max())}
        designs = {"linear": stress, "log": stress_log, "log_age2": stress_log2}
        for name, (x, names) in forms(sw, hw, age).items():
            fit = fit_poisson_glm(x, y, names)
            eta = float(np.asarray(fit.coefficients["intercept"]) +
                        np.dot(np.array([fit.coefficients[n] for n in names]), designs[name][0]))
            entry[name] = {
                "aic": float(fit.aic),
                "dispersion": float(fit.dispersion),
                "pred_p999": float(np.exp(min(eta, 30.0))),
                "coefficients": {k: float(v) for k, v in fit.coefficients.items()},
            }
        out["species"][species] = entry
        print(f"{species:9s} {entry['linear']['aic']:10.0f} {entry['log']['aic']:10.0f} "
              f"{entry['log_age2']['aic']:9.0f} {entry['linear']['dispersion']:8.2f} "
              f"{entry['log']['dispersion']:8.2f} {entry['linear']['pred_p999']:11.1f} "
              f"{entry['log']['pred_p999']:11.1f} {entry['obs_max']:7d}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
