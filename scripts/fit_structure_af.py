"""Fit bird AFs with LiDAR structure and compare against volume/age/composition.

A0  log1p(soft) + log1p(hard) + age
A1  A0 + composition
A2  A0 + LiDAR structure (height mean/p95/std, cover)
A3  A2 + 1-degree region cells (control)

Same response, effort offset, 5-fold spatial block CV by region cell.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_composition_probe import build  # noqa: E402

TERMS_A0 = "log_soft + log_hard + age"
TERMS_COMP = "pine + spruce + fir + douglas + cedar + aspen + birch"
TERMS_LIDAR = "lidar_height_mean + lidar_height_p95 + lidar_height_std + lidar_cover"


def poisson_deviance(y, mu):
    y = np.asarray(y, float)
    mu = np.maximum(np.asarray(mu, float), 1e-9)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(y > 0, y * np.log(y / mu), 0.0)
    return 2 * np.sum(term - (y - mu))


def evaluate(frame: pd.DataFrame, formula: str, bird: str, folds: int = 5) -> dict:
    offset = (np.log(frame.duration.fillna(1.0))
              + np.log1p(frame.distance.fillna(0.0))
              + np.log(frame.observers.fillna(1.0).clip(lower=1))).to_numpy()
    y, X = patsy.dmatrices(f"{bird} ~ {formula}", frame, return_type="dataframe")
    model = sm.GLM(y, X, family=sm.families.Poisson(), offset=offset).fit(maxiter=80)
    # spatial block CV by 0.5-degree cell
    cell = ((frame.lat // 0.5).astype(int) * 10000 + (frame.lon // 0.5).astype(int)).to_numpy()
    unique = np.unique(cell)
    rng = np.random.default_rng(42)
    rng.shuffle(unique)
    dev = 0.0
    for k in range(folds):
        test_cells = set(unique[k::folds].tolist())
        test = np.isin(cell, list(test_cells))
        train = ~test
        if test.sum() == 0 or train.sum() == 0:
            continue
        fit = sm.GLM(y[train], X[train], family=sm.families.Poisson(), offset=offset[train]).fit(maxiter=80)
        eta = np.asarray(X[test] @ fit.params) + offset[test]
        mu = np.exp(np.clip(eta, -30, 30))
        dev += poisson_deviance(np.asarray(y[test]).ravel(), mu)
    return {
        "aic": float(model.aic),
        "scale": float(model.scale),
        "deviance": float(model.deviance),
        "cv_deviance": float(dev),
        "cv_per_row": float(dev / len(frame)),
        "params": {name: float(value) for name, value in model.params.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lidar", type=Path, required=True)
    parser.add_argument("--birds", nargs="+", default=["gockin", "borchi2", "rebnut", "brncre", "yerwar"])
    parser.add_argument("--structure-terms", default="lidar_height_mean + lidar_height_p95 + lidar_height_std + lidar_cover")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    frame = build()
    samples = np.load("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz", allow_pickle=True)
    frame = frame.merge(pd.DataFrame({"event": samples["checklist_id"].astype(str),
                                      "lat": samples["latitude"], "lon": samples["longitude"]}),
                        on="event", how="left")
    lidar = pd.read_parquet(args.lidar).drop_duplicates("checklist_id").rename(columns={"checklist_id": "event"})
    frame = frame.merge(lidar, on="event", how="inner")
    frame = frame.dropna(subset=[*args.birds, "soft_vol", "hard_vol", "age", "duration",
                                 "lidar_height_mean", "lidar_height_p95", "lidar_height_std", "lidar_cover"])
    print(f"joined checklists with LiDAR: {len(frame):,}", flush=True)
    frame["cell"] = ((frame.lat // 1).astype(int) * 1000 + (frame.lon // 1).astype(int)).astype(str)

    results = {}
    for bird in args.birds:
        rows = {}
        for name, formula in (
            ("A0", TERMS_A0),
            ("A1", f"{TERMS_A0} + {TERMS_COMP}"),
            ("A2", f"{TERMS_A0} + {args.structure_terms}"),
            ("A3", f"{TERMS_A0} + {TERMS_COMP} + {args.structure_terms}"),
        ):
            rows[name] = evaluate(frame, formula, bird)
        results[bird] = rows
        print(f"\n{bird}: n={len(frame):,}")
        print(f"{'model':4s} {'AIC':>12s} {'CV dev/row':>11s} {'scale':>7s}")
        for name, r in rows.items():
            print(f"{name:4s} {r['aic']:12.0f} {r['cv_per_row']:11.4f} {r['scale']:7.3f}")
        lid = rows["A2"]
        print("  LiDAR terms (A2): " + ", ".join(
            f"{k}={lid['params'].get(k, 0):+.4f}" for k in args.structure_terms.split(" + ")))

    if args.out:
        import json
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
