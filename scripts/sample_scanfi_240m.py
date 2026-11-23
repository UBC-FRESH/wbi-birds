"""Sample the 240 m SCANFI neighbourhood metrics at every eBird checklist.

Pairs 2018-2022 checklists with SCANFI 2020 and 2023+ with SCANFI 2025.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import rowcol
from pyproj import Transformer

ROOT = Path("/srv/shared-data/gep/wbi-birds")
SAMPLES = ROOT / "campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz"
GRID = ROOT / "fvsbc-work/scanfi-240m"
OUT = ROOT / "fvsbc-work/scanfi-240m/checklist-metrics.npz"


def sample(path: Path, xs, ys) -> np.ndarray:
    with rasterio.open(path) as ds:
        rows, cols = rowcol(ds.transform, xs, ys)
        rows = np.asarray(rows)
        cols = np.asarray(cols)
        inside = (rows >= 0) & (rows < ds.height) & (cols >= 0) & (cols < ds.width)
        out = np.full((3, len(xs)), np.nan, dtype=np.float32)
        for band in range(1, 4):
            vals = np.full(len(xs), np.nan, dtype=np.float32)
            vals[inside] = ds.read(band, window=((rows[inside].min(), rows[inside].max() + 1),
                                                  (cols[inside].min(), cols[inside].max() + 1))
                                                  )[rows[inside] - rows[inside].min(),
                                                    cols[inside] - cols[inside].min()]
            out[band - 1] = vals
        return out


def main() -> int:
    s = np.load(SAMPLES, allow_pickle=False)
    lon = s["longitude"].astype(float)
    lat = s["latitude"].astype(float)
    year = s["year"].astype(int)
    with rasterio.open(GRID / "metrics-2020.tif") as ds:
        tr = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
    xs, ys = tr.transform(lon, lat)
    m20 = sample(GRID / "metrics-2020.tif", xs, ys)
    m25 = sample(GRID / "metrics-2025.tif", xs, ys)
    use25 = year >= 2023
    forest = np.where(use25, m25[0], m20[0]).astype(np.float32)
    edge = np.where(use25, m25[1], m20[1]).astype(np.float32)
    early = np.where(use25, m25[2], m20[2]).astype(np.float32)
    sc_year = np.where(use25, 2025, 2020).astype(np.int16)
    # 2018-2019 use the 2020 layer (nearest available); earlier years keep 2020
    # for exploratory fits but are excluded from the production 2018+ fit.
    np.savez_compressed(OUT, checklist_id=s["checklist_id"].astype(str), year=year,
                        sc_year=sc_year, pct_forest_2km=forest,
                        edge_2km=edge, pct_early_2km=early)
    ok = np.isfinite(forest) & np.isfinite(edge) & np.isfinite(early)
    print(f"wrote {OUT}: {ok.sum():,} of {len(lon):,} checklists with metrics")
    print(f"2018+ {((year >= 2018) & ok).sum():,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
