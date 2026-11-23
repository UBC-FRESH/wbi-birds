"""Build 240 m SCANFI v2 neighbourhood metrics for the checklist study area.

The 240 m grid is an exact 8 x 8 aggregation of the 30 m SCANFI cells, so the
2 km neighbourhood is an 8-cell window, matching the engine's edge window.

Outputs a 3-band GeoTIFF (forest fraction, edge fraction, early-seral fraction)
at 240 m, plus the class grid, for one SCANFI year.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window
from pyproj import Transformer
from scipy import ndimage as ndi

TS = Path("/srv/shared-data/gep/wbi-birds/fvsbc-work/scanfi-ts")
ANNEX = Path("/srv/shared-data/gep/jupyterhub16-projects/clews-c2070-fresh/data/raw/scanfi/v2")
SAMPLES = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz")
CELL = 240
BLOCK = 8
WINDOW = 8
EARLY_AGE = 40.0
MATURE_AGE = 80.0


def paths(year: int) -> tuple[Path, Path]:
    if year == 2025:
        return (ANNEX / "SCANFI_age_median_2025_v2_20260119.tif",
                ANNEX / "SCANFI_att_biomass_2025_v2_20260119.tif")
    return (TS / f"SCANFI_age_median_{year}_v2_20260119.tif",
            TS / f"SCANFI_att_biomass_{year}_v2_20260119.tif")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--buffer", type=float, default=5000.0)
    ap.add_argument("--chunk-rows", type=int, default=80)
    args = ap.parse_args()

    age_p, bio_p = paths(args.year)
    sample = np.load(SAMPLES, allow_pickle=False)
    lon = sample["longitude"].astype(float)
    lat = sample["latitude"].astype(float)

    with rasterio.open(age_p) as a:
        tr = Transformer.from_crs("EPSG:4326", a.crs, always_xy=True)
        xs, ys = tr.transform(lon, lat)
        x0 = float(np.percentile(xs, 1)) - args.buffer
        x1 = float(np.percentile(xs, 99)) + args.buffer
        y0 = float(np.percentile(ys, 1)) - args.buffer
        y1 = float(np.percentile(ys, 99)) + args.buffer
        c = a.transform.c; f = a.transform.f; res = a.transform.a
        col0 = max(0, int((x0 - c) / res) // BLOCK * BLOCK)
        col1 = min(a.width, int((x1 - c) / res) + BLOCK)
        row0 = max(0, int((f - y1) / res) // BLOCK * BLOCK)
        row1 = min(a.height, int((f - y0) / res) + BLOCK)
        width = (col1 - col0) // BLOCK * BLOCK
        height = (row1 - row0) // BLOCK * BLOCK
        gw, gh = width // BLOCK, height // BLOCK
        print(f"30 m window rows {row0}:{row0+height} cols {col0}:{col0+width} -> {gh}x{gw} cells", flush=True)
        transform = from_origin(c + col0 * res, f - row0 * res, CELL, CELL)

        age_sum = np.zeros((gh, gw), np.float64)
        bio_sum = np.zeros((gh, gw), np.float64)
        cnt = np.zeros((gh, gw), np.int32)
        with rasterio.open(bio_p) as b:
            for r in range(row0, row0 + height, args.chunk_rows):
                nr = min(args.chunk_rows, row0 + height - r)
                win = Window(col0, r, width, nr)
                age = a.read(1, window=win)
                bio = b.read(1, window=win)
                valid = (age > 0) & (age != 32767) & (bio > 0) & (bio != 32767)
                age = np.where(valid, age, 0).astype(np.float32)
                bio = np.where(valid, bio, 0).astype(np.float32)
                hh = nr // BLOCK
                if hh == 0:
                    continue
                age = age[:hh * BLOCK].reshape(hh, BLOCK, gw, BLOCK).sum(axis=(1, 3))
                bio = bio[:hh * BLOCK].reshape(hh, BLOCK, gw, BLOCK).sum(axis=(1, 3))
                vv = valid[:hh * BLOCK].reshape(hh, BLOCK, gw, BLOCK).sum(axis=(1, 3))
                i0 = (r - row0) // BLOCK
                age_sum[i0:i0 + hh] = age
                bio_sum[i0:i0 + hh] = bio
                cnt[i0:i0 + hh] = vv
                if (i0 // 10) % 10 == 0:
                    print(f"  rows {r-row0}/{height}", flush=True)

    valid_frac = cnt / float(BLOCK * BLOCK)
    age_m = np.divide(age_sum, cnt, out=np.zeros_like(age_sum), where=cnt > 0)
    bio_m = np.divide(bio_sum, cnt, out=np.zeros_like(bio_sum), where=cnt > 0)
    forest = (valid_frac >= 0.5) & (age_m > 0)
    classes = np.full((gh, gw), -1, dtype=np.int8)
    classes[forest & (age_m < EARLY_AGE)] = 0
    classes[forest & (age_m >= EARLY_AGE) & (age_m < MATURE_AGE)] = 1
    classes[forest & (age_m >= MATURE_AGE)] = 2

    early = (classes == 0).astype(np.float32)
    boundary = np.zeros_like(early)
    boundary[:-1, :] += (classes[:-1, :] != classes[1:, :])
    boundary[1:, :] += (classes[1:, :] != classes[:-1, :])
    boundary[:, :-1] += (classes[:, :-1] != classes[:, 1:])
    boundary[:, 1:] += (classes[:, 1:] != classes[:, :-1])
    edge = ndi.uniform_filter((boundary > 0).astype(np.float32), size=WINDOW, mode="nearest")
    early_f = ndi.uniform_filter(early, size=WINDOW, mode="nearest")
    forest_f = ndi.uniform_filter(forest.astype(np.float32), size=WINDOW, mode="nearest")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="GTiff", width=gw, height=gh, count=3, dtype="float32",
                   crs=a.crs, transform=transform, tiled=True, blockxsize=256,
                   blockysize=256, compress="deflate", predictor=2)
    with rasterio.open(args.out, "w", **profile) as dst:
        dst.write(forest_f.astype(np.float32), 1)
        dst.write(edge.astype(np.float32), 2)
        dst.write(early_f.astype(np.float32), 3)
    cls_out = args.out.with_name(args.out.stem + "-class.tif")
    with rasterio.open(cls_out, "w", **{**profile, "count": 1, "dtype": "int8"}) as dst:
        dst.write(classes, 1)
    print(f"wrote {args.out} ({gh}x{gw}) and {cls_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
