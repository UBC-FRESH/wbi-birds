"""Probe: does species composition add response structure beyond volume + age?

Rebuilds the checklist table from the derived eBird extract (counts) and the kNN
samples (20 species percentages, volume, age), then fits quasi-Poisson GLMs:

    M0  log(count) ~ log1p(softwood volume) + log1p(hardwood volume) + age
    M1  M0 + conifer/deciduous composition groups
    M2  composition only

and compares AIC, dispersion, and the implied age response at fixed composition.

Usage:
    python scripts/fit_composition_probe.py --bird gockin
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

DERIVED = Path("/srv/shared-data/gep/wbi-birds/wbi-ebird-data/derived/world-2026-09")
SAMPLES = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz")
SPATIAL = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/knn-v0/spatial-covariates-study-area.npz")

CODES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
NAME2CODE = {
    "Red-breasted Nuthatch": "rebnut", "Boreal Chickadee": "borchi2",
    "Golden-crowned Kinglet": "gockin", "Brown Creeper": "brncre",
    "Yellow-rumped Warbler": "yerwar", "Swainson's Thrush": "swathr",
    "White-throated Sparrow": "whtspa", "Tennessee Warbler": "tenwar",
    "Yellow-bellied Sapsucker": "yebsap",
}
SPECIES = ["Pice_Eng", "Pice_Gla", "Pice_Mar", "Pinu_Con", "Pseu_Men", "Abie_Las", "Pinu_Mon",
           "Tsug_Mer", "Lari_Lya", "Pinu_Alb", "Pice_Spp", "Abie_Ama", "Lari_Lar", "Tsug_Het",
           "Abie_Bal", "Thuj_Pli", "Popu_Tre", "Popu_Spp", "Sali_Spp", "Popu_Tri", "Betu_Pap"]
CONIFER = ["Pice_Eng", "Pice_Gla", "Pice_Mar", "Pinu_Con", "Pseu_Men", "Abie_Las", "Pinu_Mon",
           "Tsug_Mer", "Lari_Lya", "Pinu_Alb", "Pice_Spp", "Abie_Ama", "Lari_Lar", "Tsug_Het",
           "Abie_Bal", "Thuj_Pli"]
DECID = ["Popu_Tre", "Popu_Spp", "Sali_Spp", "Popu_Tri", "Betu_Pap"]


def build() -> pd.DataFrame:
    s = np.load(SAMPLES, allow_pickle=True)
    spatial = np.load(SPATIAL, allow_pickle=True)
    frame = pd.DataFrame({k: np.asarray(s[k], dtype=np.float32) for k in SPECIES + ["mvol", "age"]})
    frame["event"] = s["checklist_id"].astype(str)
    for key in spatial.files:
        frame[key] = np.asarray(spatial[key], dtype=np.float32)

    sed = pd.read_csv(DERIVED / "sed_bc_breeding.tsv", sep="\t",
                      usecols=["SAMPLING EVENT IDENTIFIER", "PROTOCOL NAME", "DURATION MINUTES",
                               "EFFORT DISTANCE KM", "NUMBER OBSERVERS", "ALL SPECIES REPORTED"])
    sed = sed.rename(columns={"SAMPLING EVENT IDENTIFIER": "event", "PROTOCOL NAME": "protocol",
                              "DURATION MINUTES": "duration", "EFFORT DISTANCE KM": "distance",
                              "NUMBER OBSERVERS": "observers", "ALL SPECIES REPORTED": "complete"})
    sed["event"] = sed["event"].astype(str)
    sed["complete"] = pd.to_numeric(sed["complete"], errors="coerce")
    sed["duration"] = pd.to_numeric(sed["duration"], errors="coerce")
    sed["distance"] = pd.to_numeric(sed["distance"], errors="coerce")
    sed["observers"] = pd.to_numeric(sed["observers"], errors="coerce")
    sed = sed[(sed.complete == 1) & sed.protocol.isin(["Traveling", "Stationary"]) & (sed.duration > 0)]

    ebd = pd.read_csv(DERIVED / "ebd_bc_suite_breeding.tsv", sep="\t",
                      usecols=["SAMPLING EVENT IDENTIFIER", "COMMON NAME", "OBSERVATION COUNT",
                               "ALL SPECIES REPORTED"])
    ebd = ebd.rename(columns={"SAMPLING EVENT IDENTIFIER": "event", "COMMON NAME": "name",
                              "OBSERVATION COUNT": "count", "ALL SPECIES REPORTED": "complete"})
    ebd["event"] = ebd["event"].astype(str)
    ebd["complete"] = pd.to_numeric(ebd["complete"], errors="coerce")
    ebd["count"] = pd.to_numeric(ebd["count"], errors="coerce").fillna(0)
    ebd = ebd[(ebd.complete == 1) & ebd.name.isin(NAME2CODE)]
    ebd["code"] = ebd.name.map(NAME2CODE)
    counts = ebd.groupby(["event", "code"], observed=True)["count"].sum().unstack(fill_value=0).reset_index()

    frame = frame.merge(counts, on="event", how="inner").merge(sed, on="event", how="inner")
    for code in CODES:
        if code not in frame:
            frame[code] = 0
        frame[code] = frame[code].astype(float)

    # composition fractions (percent -> fraction); missing -> 0
    for col in SPECIES:
        frame[col] = frame[col].fillna(0.0) / 100.0
    frame["conifer"] = frame[CONIFER].sum(axis=1)
    frame["decid"] = frame[DECID].sum(axis=1)
    frame["pine"] = frame[["Pinu_Con", "Pinu_Mon", "Pinu_Alb"]].sum(axis=1)
    frame["spruce"] = frame[["Pice_Eng", "Pice_Gla", "Pice_Mar", "Pice_Spp"]].sum(axis=1)
    frame["fir"] = frame[["Abie_Las", "Abie_Ama", "Abie_Bal"]].sum(axis=1)
    frame["douglas"] = frame["Pseu_Men"]
    frame["cedar"] = frame[["Thuj_Pli", "Tsug_Mer", "Tsug_Het"]].sum(axis=1)
    frame["aspen"] = frame["Popu_Tre"]
    frame["birch"] = frame["Betu_Pap"]
    frame["soft_vol"] = frame["mvol"] * frame["conifer"]
    frame["hard_vol"] = frame["mvol"] * frame["decid"]
    frame["log_soft"] = np.log1p(frame["soft_vol"])
    frame["log_hard"] = np.log1p(frame["hard_vol"])
    frame["log_effort"] = np.log(frame["duration"]) + np.log1p(frame["distance"]) + np.log(frame["observers"].clip(lower=1))
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bird", default="gockin")
    parser.add_argument("--sample", type=int, default=0, help="optional row sample for speed")
    args = parser.parse_args()

    frame = build()
    print(f"joined checklists: {len(frame):,}; {args.bird} mean count {frame[args.bird].mean():.3f}", flush=True)
    frame = frame.dropna(subset=[args.bird, "soft_vol", "hard_vol", "age"])
    print(f"complete rows: {len(frame):,}", flush=True)
    data = frame.sample(args.sample, random_state=42) if args.sample else frame
    offset = data["log_effort"].to_numpy()

    def fit(formula: str):
        model = smf.glm(formula, data, family=sm.families.Poisson(), offset=offset).fit(maxiter=60)
        return model

    m0 = fit(f"{args.bird} ~ log_soft + log_hard + age")
    m1 = fit(f"{args.bird} ~ log_soft + log_hard + age + pine + spruce + fir + douglas + cedar + aspen + birch")
    m2 = fit(f"{args.bird} ~ pine + spruce + fir + douglas + cedar + aspen + birch + age")
    m3 = fit(f"{args.bird} ~ log_soft + log_hard + age + pine + spruce + fir + douglas + cedar + aspen + birch"
             f" + age:spruce + age:pine + age:aspen + age:cedar")

    print(f"\n{'model':4s} {'AIC':>12s} {'scale':>8s} {'dev_expl':>9s}")
    for name, model in (("M0", m0), ("M1", m1), ("M2", m2), ("M3", m3)):
        print(f"{name:4s} {model.aic:12.1f} {model.scale:8.3f} {1 - model.deviance/model.null_deviance:9.3f}")
    print(f"\ndAIC M1-M0: {m1.aic - m0.aic:+.1f};  M2-M0: {m2.aic - m0.aic:+.1f};  M3-M1: {m3.aic - m1.aic:+.1f}")

    print("\nM1 composition terms:")
    for term in ("pine", "spruce", "fir", "douglas", "cedar", "aspen", "birch"):
        print(f"  {term:8s} {m1.params[term]:+8.3f}  se {m1.bse[term]:.3f}  p {m1.pvalues[term]:.2e}")

    ages = np.array([0, 20, 40, 80, 120, 160, 200, 250, 300])
    base = {
        "log_soft": float(np.log1p(np.nanmedian(frame["soft_vol"]))),
        "log_hard": float(np.log1p(np.nanmedian(frame["hard_vol"]))),
        "pine": float(np.nanmedian(frame["pine"])), "spruce": float(np.nanmedian(frame["spruce"])),
        "fir": float(np.nanmedian(frame["fir"])), "douglas": float(np.nanmedian(frame["douglas"])),
        "cedar": float(np.nanmedian(frame["cedar"])), "aspen": float(np.nanmedian(frame["aspen"])),
        "birch": float(np.nanmedian(frame["birch"])),
    }
    print("\nage response at median composition (counts per checklist, offset 0):")
    print(f"{'age':>5s} {'M0':>9s} {'M1':>9s} {'M1/M0':>7s} {'M3':>9s}")
    for age in ages:
        eta0 = m0.params["Intercept"] + m0.params["log_soft"] * base["log_soft"] + m0.params["log_hard"] * base["log_hard"] + m0.params["age"] * age
        eta1 = (m1.params["Intercept"] + m1.params["log_soft"] * base["log_soft"] + m1.params["log_hard"] * base["log_hard"]
                + m1.params["age"] * age + sum(m1.params[t] * base[t] for t in ("pine", "spruce", "fir", "douglas", "cedar", "aspen", "birch")))
        eta3 = (m3.params["Intercept"] + m3.params["log_soft"] * base["log_soft"] + m3.params["log_hard"] * base["log_hard"]
                + m3.params["age"] * age + sum(m3.params[t] * base[t] for t in ("pine", "spruce", "fir", "douglas", "cedar", "aspen", "birch"))
                + age * (m3.params["age:spruce"] * base["spruce"] + m3.params["age:pine"] * base["pine"]
                         + m3.params["age:aspen"] * base["aspen"] + m3.params["age:cedar"] * base["cedar"]))
        print(f"{age:5d} {np.exp(eta0):9.3f} {np.exp(eta1):9.3f} {np.exp(eta1 - eta0):7.2f} {np.exp(eta3):9.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
