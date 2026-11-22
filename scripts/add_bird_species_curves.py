"""Add the nine-species bird curves to a compiled ws4 dataset.

This follows the original RBNU feature method: sw and hw are the track's species
yield curves summed over the contract's wood types (deciduous AT/AC/ACT/EP are
hardwood, every other code is conifer), interpolated on the union age grid, and

    bird_s = exp(b0_s + b_sw_s*sw + b_hw_s*hw + b_age_s*age)

eta is clipped to the observed calibration maximum for that species, so a
linear-volume log link cannot extrapolate to absurd densities on high-volume
planning tracks.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
# Deciduous codes (contract hardwood: Populus / Salix / Betula).  Everything else in
# the dataset is a conifer (contract softwood).  The earlier ad-hoc sets only matched
# one TSA's code list and silently dropped SW/PL/SB/S on the others.
HARDWOOD = ("AT", "AC", "ACT", "EP")
LABEL_PREFIX = "feature.Bird."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--fits", type=Path, required=True)
    parser.add_argument("--account-group", default="_MANAGED_")
    parser.add_argument("--backup", type=Path, default=None)
    args = parser.parse_args()

    dataset = args.dataset
    fits = json.loads(args.fits.read_text())["species"]

    features = pd.read_parquet(dataset / "features.parquet")
    curves = pd.read_parquet(dataset / "curves.parquet")
    accounts = pd.read_parquet(dataset / "accounts.parquet")

    backup = args.backup or dataset.parent / "compiled-bird-backup"
    backup.mkdir(parents=True, exist_ok=True)
    for name in ("features.parquet", "curves.parquet", "accounts.parquet"):
        target = backup / name
        if not target.exists():
            shutil.copy2(dataset / name, target)

    curve_xy = {
        int(cid): (g.x.to_numpy(float), g.y.to_numpy(float))
        for cid, g in curves.groupby("curve_id")
    }
    by_track: dict[int, dict[str, int]] = defaultdict(dict)
    for track, label, cid in zip(features.track_id, features.label, features.curve_id):
        by_track[int(track)][str(label)] = int(cid)

    next_curve = int(curves.curve_id.max()) + 1
    new_curves: list[pd.DataFrame] = []
    new_features: list[dict] = []
    covered = 0
    for track, labels in sorted(by_track.items()):
        species_curves = {}
        for label, cid in labels.items():
            if not label.startswith("feature.Yield."):
                continue
            parts = label.split(".")
            if len(parts) < 4:
                continue
            spp = parts[-1]
            if spp != "Total":
                ifm = parts[-2]
                previous = species_curves.get(spp)
                if previous is None or ifm == "managed":
                    species_curves[spp] = cid
        xs = {0.0}
        for cid in species_curves.values():
            xs.update(float(x) for x in curve_xy[cid][0])
        grid = np.asarray(sorted(xs), dtype=float)
        soft = np.zeros_like(grid)
        hard = np.zeros_like(grid)
        for spp, cid in species_curves.items():
            x, y = curve_xy[cid]
            values = np.interp(grid, x, y, left=0.0, right=y[-1])
            (hard if spp in HARDWOOD else soft)[:] += values
        for species in SPECIES:
            coef = fits[species]["fit"]["coefficients"]
            cap = float(fits[species].get("eta_cap", 30.0))
            if fits[species].get("covariate_form") == "log1p":
                eta = (
                    coef["intercept"]
                    + coef["softwood"] * np.log1p(soft)
                    + coef["hardwood"] * np.log1p(hard)
                    + coef["age"] * grid
                )
            else:
                eta = (
                    coef["intercept"]
                    + coef["softwood"] * soft
                    + coef["hardwood"] * hard
                    + coef["age"] * grid
                )
            bird = np.exp(np.clip(eta, -30.0, cap))
            new_curves.append(pd.DataFrame({"curve_id": next_curve, "x": grid, "y": bird}))
            new_features.append(
                {"track_id": track, "label": f"{LABEL_PREFIX}{species}", "curve_id": next_curve}
            )
            next_curve += 1
        covered += 1

    curves = pd.concat([curves, *new_curves], ignore_index=True)
    keep = ~features.label.astype(str).str.startswith(LABEL_PREFIX)
    features = pd.concat(
        [features[keep], pd.DataFrame(new_features)], ignore_index=True
    ).sort_values(["track_id", "label"]).reset_index(drop=True)
    accounts = accounts[
        ~accounts.account.astype(str).str.startswith(LABEL_PREFIX)
    ]
    accounts = pd.concat(
        [
            accounts,
            pd.DataFrame(
                {
                    "group": [args.account_group] * len(SPECIES),
                    "attribute": [f"{LABEL_PREFIX}{s}" for s in SPECIES],
                    "account": [f"{LABEL_PREFIX}{s}" for s in SPECIES],
                    "sum": [1.0] * len(SPECIES),
                }
            ),
        ],
        ignore_index=True,
    )

    features.to_parquet(dataset / "features.parquet", index=False)
    curves.to_parquet(dataset / "curves.parquet", index=False)
    accounts.to_parquet(dataset / "accounts.parquet", index=False)
    print(
        f"{dataset.name}: tracks={covered} curves={len(new_curves)} "
        f"features={len(new_features)} accounts={len(SPECIES)} backup={backup}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
