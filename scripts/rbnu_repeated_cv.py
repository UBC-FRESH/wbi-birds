"""Repeated spatial-block cross-validation for the RBNU anticipation function.

Reads a per-checklist frame (one row per checklist, with the aspatial and
neighbourhood covariates) and compares the aspatial model with models that add
forest/edge/early-seral fractions at each neighbourhood radius.

The single 5-fold partition used in the exploratory probe is noisy; this script
repeats the partition and reports the mean and standard deviation of the CV
deviance per row, plus the paired gain over the aspatial model.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm

RADII = {1: "30m", 2: "60m", 4: "120m", 8: "240m", 17: "510m", 34: "1020m", 67: "2010m"}


def offset(d: pd.DataFrame) -> np.ndarray:
    return (np.log(d.duration.fillna(1.0))
            + np.log1p(d.distance.fillna(0.0))
            + np.log(d.observers.fillna(1.0).clip(lower=1))).to_numpy()


def prep(formula: str, d: pd.DataFrame):
    y, X = patsy.dmatrices(f"rebnut ~ {formula}", d, return_type="dataframe")
    o = offset(d)
    cell = ((d.lat // 0.5).astype(int) * 10000 + (d.lon // 0.5).astype(int)).to_numpy()
    return y, X, o, cell


def cv_once(y, X, o, cell, seed: int, folds: int = 5) -> float:
    u = np.unique(cell)
    rng = np.random.default_rng(seed)
    rng.shuffle(u)
    dev = 0.0
    for k in range(folds):
        test = np.isin(cell, u[k::folds])
        train = ~test
        if test.sum() == 0 or train.sum() == 0:
            continue
        fit = sm.GLM(y[train], X[train], family=sm.families.Poisson(),
                     offset=o[train]).fit(maxiter=60)
        mu = np.exp(np.clip(np.asarray(X[test] @ fit.params) + o[test], -30, 30))
        yy = np.asarray(y[test]).ravel()
        mu = np.maximum(mu, 1e-9)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(yy > 0, yy * np.log(yy / mu), 0.0)
        dev += 2 * np.sum(t - (yy - mu))
    return float(dev / len(y))


def window(d: pd.DataFrame, name: str) -> pd.DataFrame:
    if name == "all":
        return d
    if name.endswith("+"):
        return d[d.year >= int(name[:-1])]
    if "-" in name:
        lo, hi = name.split("-")
        return d[(d.year >= int(lo)) & (d.year <= int(hi))]
    raise ValueError(f"unknown window {name!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("frame", type=Path)
    ap.add_argument("--windows", default="all,2010+,2020+,2010-2019,2020-2022,2023+")
    ap.add_argument("--radii", default="60m,120m,240m,510m,1020m")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--year-term", action="store_true")
    ap.add_argument("--suffix", default="", help="covariate suffix, e.g. _2025")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    df = pd.read_csv(args.frame)
    df["year_c"] = (df.year - df.year.mean()) / max(df.year.std(), 1e-9)
    yt = " + year_c" if args.year_term else ""
    base = "log_soft + log_hard + age" + yt
    models = {"base": base}
    for name in args.radii.split(","):
        models[name] = (base + f" + forest_{name}{args.suffix} + edge_{name}{args.suffix}"
                        + f" + early_{name}{args.suffix}")

    rows = []
    for wname in args.windows.split(","):
        d = window(df, wname.strip())
        if len(d) < 50:
            print(f"skip {wname}: n={len(d)}")
            continue
        print(f"\n== {wname} n={len(d)}", flush=True)
        pre = {k: prep(f, d) for k, f in models.items()}
        res = {k: np.array([cv_once(*pre[k], seed=s) for s in range(args.seeds)])
               for k in models}
        b = res["base"]
        for k in models:
            gain = b - res[k]
            row = dict(window=wname, model=k + args.suffix, n=len(d),
                       cv_mean=res[k].mean(), cv_sd=res[k].std(ddof=1),
                       gain_mean=gain.mean(), gain_sd=gain.std(ddof=1))
            rows.append(row)
            print(f"  {k:6s} cv {row['cv_mean']:.4f} sd {row['cv_sd']:.4f}  "
                  f"gain {row['gain_mean']:+.4f} sd {row['gain_sd']:.4f}", flush=True)

    out = args.out or Path(str(args.frame).replace(".csv", "-repeated-cv.csv"))
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
