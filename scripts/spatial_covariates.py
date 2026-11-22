"""Neighbourhood habitat covariates at eBird checklist locations.

Metrics (250 m kNN v0 rasters, BC window):
  pct_forest_1km    fraction forest within ~2 km (8-cell window)
  edge_1km          boundary-cell fraction within ~2 km (forest/non-forest edge proxy)
  pct_early_500m    fraction of early-seral forest (age < 40) within ~500 m
  mature_patch_ha   area of the connected mature-forest patch containing the point
  dist_mature_m     distance to the nearest mature forest (age >= 80)

    python scripts/spatial_covariates.py --samples <npz> --tif-dir <dir> --out <npz>
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from scipy import ndimage as ndi

CELL_M = 250.0
CELL_HA = (CELL_M * CELL_M) / 10_000.0
MATURE_AGE = 80.0
EARLY_AGE = 40.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--tif-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mature-age", type=float, default=MATURE_AGE)
    parser.add_argument("--early-age", type=float, default=EARLY_AGE)
    args = parser.parse_args()

    sample = np.load(args.samples, allow_pickle=False)
    lon = sample["longitude"].astype(float)
    lat = sample["latitude"].astype(float)

    age_path = args.tif_dir / "NFI_MODIS250m_kNN_Structure_Stand_Age_v0.tif"
    vol_path = args.tif_dir / "NFI_MODIS250m_kNN_Structure_Volume_Merch_v0.tif"
    with rasterio.open(age_path) as src:
        crs = src.crs
        xs, ys = warp_transform("EPSG:4326", crs, lon.tolist(), lat.tolist())
        from rasterio.transform import rowcol
        rows, cols = rowcol(src.transform, xs, ys)
        rows = np.asarray(rows); cols = np.asarray(cols)
        margin = 40
        col0 = max(0, int(cols.min()) - margin); col1 = min(src.width, int(cols.max()) + margin + 1)
        row0 = max(0, int(rows.min()) - margin); row1 = min(src.height, int(rows.max()) + margin + 1)
        window = rasterio.windows.Window(col0, row0, col1 - col0, row1 - row0)
        age = src.read(1, window=window).astype(np.float32)
        nod = src.nodata
    with rasterio.open(vol_path) as src:
        vol = src.read(1, window=window).astype(np.float32)
        nod2 = src.nodata
    print(f"window {age.shape} cells", flush=True)

    age = np.where(np.isfinite(age) & (age != (nod if nod is not None else -1)), age, -1)
    vol = np.where(np.isfinite(vol) & (vol != (nod2 if nod2 is not None else -1)), vol, -1)
    forest = (age > 0) & (vol > 0)
    mature = forest & (age >= args.mature_age)
    early = forest & (age < args.early_age)
    print(f"forest {forest.mean():.2%} mature {mature.mean():.2%} early {early.mean():.2%}", flush=True)

    t = time.time()
    pct_forest = ndi.uniform_filter(forest.astype(np.float32), size=8, mode="nearest")
    pct_early = ndi.uniform_filter(early.astype(np.float32), size=2, mode="nearest")
    # edge proxy: forest cell with at least one 4-neighbour of different class
    b = np.zeros_like(forest, dtype=np.float32)
    b[:-1, :] += (forest[:-1, :] != forest[1:, :])
    b[1:, :] += (forest[1:, :] != forest[:-1, :])
    b[:, :-1] += (forest[:, :-1] != forest[:, 1:])
    b[:, 1:] += (forest[:, 1:] != forest[:, :-1])
    edge = ndi.uniform_filter((b > 0).astype(np.float32), size=8, mode="nearest")
    print(f"window metrics {time.time()-t:.0f}s", flush=True)

    t = time.time()
    labels, count = ndi.label(mature, structure=np.ones((3, 3), dtype=int))
    patch_area = np.bincount(labels.ravel()) * CELL_HA
    patch_cells = patch_area[labels]
    dist = ndi.distance_transform_edt(~mature) * CELL_M
    print(f"patch+distance {time.time()-t:.0f}s ({count} mature patches)", flush=True)

    rr = rows - row0
    cc = cols - col0
    inside = (rr >= 0) & (rr < age.shape[0]) & (cc >= 0) & (cc < age.shape[1])
    out = {
        "pct_forest_1km": np.full(len(lon), np.nan, dtype=np.float32),
        "edge_1km": np.full(len(lon), np.nan, dtype=np.float32),
        "pct_early_500m": np.full(len(lon), np.nan, dtype=np.float32),
        "mature_patch_ha": np.full(len(lon), np.nan, dtype=np.float32),
        "dist_mature_m": np.full(len(lon), np.nan, dtype=np.float32),
    }
    out["pct_forest_1km"][inside] = pct_forest[rr[inside], cc[inside]]
    out["edge_1km"][inside] = edge[rr[inside], cc[inside]]
    out["pct_early_500m"][inside] = pct_early[rr[inside], cc[inside]]
    out["mature_patch_ha"][inside] = patch_cells[rr[inside], cc[inside]]
    out["dist_mature_m"][inside] = dist[rr[inside], cc[inside]]
    print(f"sampled {inside.sum():,} of {len(lon):,}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, **out)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
