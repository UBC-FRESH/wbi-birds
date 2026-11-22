"""Per-period bird totals under a schedule, aspatial vs spatial AF (vectorised).

    python scripts/spatial_bird_totals.py --dataset <dir> --geometry <feather> \
        --fits-aspatial <json> --fits-spatial <json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import wkb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_evaluator import RasterState, classify  # noqa: E402

SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
HARD = {"AT", "AC", "ACT", "EP"}
YEARS, PERIOD = 200, 10
PERIODS = YEARS // PERIOD
MAX_AGE = 300


def volume_matrices(dataset: Path) -> tuple[np.ndarray, np.ndarray]:
    feats = pd.read_parquet(dataset / "features.parquet")
    curves = pd.read_parquet(dataset / "curves.parquet")
    max_track = int(feats.track_id.max())
    sw = np.zeros((max_track + 1, MAX_AGE + 1), dtype=np.float32)
    hw = np.zeros((max_track + 1, MAX_AGE + 1), dtype=np.float32)
    grid = np.arange(MAX_AGE + 1, dtype=float)
    for track, rows in feats.groupby("track_id"):
        for label, cid in zip(rows.label, rows.curve_id):
            parts = str(label).split(".")
            if len(parts) == 4 and parts[0] == "feature" and parts[1] == "Yield" and parts[3] != "Total":
                c = curves[curves.curve_id == int(cid)].sort_values("x")
                values = np.interp(grid, c.x.to_numpy(float), c.y.to_numpy(float),
                                   left=0.0, right=float(c.y.iloc[-1]))
                target = hw if parts[3] in HARD else sw
                target[int(track), :] += values
    return sw, hw


def block_means(values: np.ndarray, cell_block: np.ndarray, counts: np.ndarray, n: int) -> np.ndarray:
    valid = cell_block >= 0
    total = np.bincount(cell_block[valid], weights=values.ravel()[valid], minlength=n)
    return (total / np.maximum(counts, 1)).astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--fits-aspatial", type=Path, required=True)
    parser.add_argument("--fits-spatial", type=Path, required=True)
    args = parser.parse_args()

    frag = pd.read_parquet(args.dataset / "fragments.parquet")
    n = len(frag)
    initial = frag["age"].to_numpy(float)
    area = frag["area_ha"].to_numpy(float)
    track = frag["track_id"].to_numpy(int)
    SW, HW = volume_matrices(args.dataset)
    geo = pd.read_feather(args.geometry)
    geoms = [wkb.loads(x) for x in geo.geometry]

    treat = pd.read_parquet(args.dataset / "treatments.parquet")
    managed = set(int(t) for t in treat.track_id.unique())
    schedule = {i: 0.0 for i in range(n) if track[i] in managed and initial[i] >= 80}
    print(f"blocks {n}  treated {len(schedule)}")

    asp = json.loads(args.fits_aspatial.read_text())["species"]
    spa = json.loads(args.fits_spatial.read_text())["species"]
    st = RasterState.build(geoms, n, initial)
    cell_block = st.block_grid.ravel()
    counts = np.bincount(cell_block[cell_block >= 0], minlength=n)

    print(f"{'period':>6s} {'aspatial_M':>12s} {'spatial_M':>12s} {'ratio':>7s}")
    for period in range(PERIODS):
        t = (period + 1) * PERIOD
        age = initial + t
        for block, year in schedule.items():
            age[block] = t - year
        st.class_of_block = classify(np.minimum(age, 400.0))
        st.recompute()
        early = block_means(st.early.ravel(), cell_block, counts, n)
        edge = block_means(st.edge.ravel(), cell_block, counts, n)
        age = np.minimum(age, MAX_AGE)
        age_clip = age.astype(int)
        sw = SW[track, age_clip]
        hw = HW[track, age_clip]
        tot_a = tot_s = 0.0
        for sp in SPECIES:
            cb = asp[sp]["fit"]["coefficients"]
            cs = spa[sp]["coefficients"]
            eta_a = cb["intercept"] + cb["softwood"] * np.log1p(sw) + cb["hardwood"] * np.log1p(hw) + cb["age"] * age
            eta_s = (cs["intercept"] + cs["log1p_softwood"] * np.log1p(sw) + cs["log1p_hardwood"] * np.log1p(hw)
                     + cs["age"] * age + cs["pct_forest_1km"] + cs["edge_1km"] * edge + cs["pct_early_500m"] * early)
            tot_a += float(np.sum(area * np.exp(np.clip(eta_a, -30, asp[sp]["eta_cap"]))))
            tot_s += float(np.sum(area * np.exp(np.clip(eta_s, -30, spa[sp]["eta_cap"]))))
        print(f"{period+1:6d} {tot_a/1e6:12.3f} {tot_s/1e6:12.3f} {tot_s/max(tot_a,1e-9):7.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
