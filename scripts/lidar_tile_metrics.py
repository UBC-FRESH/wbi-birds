"""Download LiDAR DSM/DEM tiles and compute 250 m structure metrics at checklists.

    python scripts/lidar_tile_metrics.py --tiles lidar/tsa41-tiles.tsv --limit 400 \
      --cache lidar/cache --out lidar/checklist-metrics-tsa41.parquet
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer

SAMPLES = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz")
BLOCK = 250
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:6653", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:6653", "EPSG:4326", always_xy=True)


def fetch(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl", "-s", "--max-time", "300", "-o", str(path), url], check=True)


def block_stats(chm: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Mean, p95, canopy cover, and std on BLOCK x BLOCK cells."""
    h, w = chm.shape
    rows, cols = h // BLOCK, w // BLOCK
    trimmed = chm[: rows * BLOCK, : cols * BLOCK].reshape(rows, BLOCK, cols, BLOCK)
    trimmed = trimmed.transpose(0, 2, 1, 3).reshape(rows, cols, BLOCK * BLOCK)
    valid = np.isfinite(trimmed) & (trimmed > -1.0) & (trimmed < 80.0)
    counts = valid.sum(axis=2)
    safe = np.where(valid, trimmed, 0.0)
    mean = np.where(counts > 0, safe.sum(axis=2) / np.maximum(counts, 1), np.nan)
    cover = np.where(counts > 0, ((safe > 2.0) & valid).sum(axis=2) / np.maximum(counts, 1), np.nan)
    p95 = np.full((rows, cols), np.nan)
    std = np.full((rows, cols), np.nan)
    for r in range(rows):
        for c in range(cols):
            v = safe[r, c][valid[r, c]]
            if v.size:
                p95[r, c] = np.percentile(v, 95)
                std[r, c] = v.std()
    return mean, p95, cover, std


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiles", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sample = np.load(SAMPLES, allow_pickle=True)
    ids = sample["checklist_id"].astype(str)
    lat = sample["latitude"].astype(float)
    lon = sample["longitude"].astype(float)
    x, y = TO_UTM.transform(lon, lat)

    tiles = pd.read_csv(args.tiles, sep="\t", header=None,
                        names=["n", "x0", "x1", "y0", "y1", "filename", "s3Url", "demUrl"])
    tiles = tiles[tiles.n > 0].head(args.limit)
    print(f"processing {len(tiles):,} tiles with {int(tiles.n.sum()):,} checklists", flush=True)

    rows = []
    for k, tile in enumerate(tiles.itertuples(), start=1):
        dsm_path = args.cache / tile.filename
        dem_path = args.cache / Path(tile.demUrl).name
        try:
            fetch(tile.s3Url, dsm_path)
            fetch(tile.demUrl, dem_path)
            with rasterio.open(dsm_path) as d, rasterio.open(dem_path) as e:
                chm = d.read(1).astype(float) - e.read(1).astype(float)
                transform = d.transform
            mean, p95, cover, std = block_stats(chm)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {tile.filename}: {exc}", flush=True)
            continue
        inside = (lon >= tile.x0) & (lon <= tile.x1) & (lat >= tile.y0) & (lat <= tile.y1)
        for i in np.nonzero(inside)[0]:
            col, row = ~transform * (x[i], y[i])
            r, c = int(row // BLOCK), int(col // BLOCK)
            if 0 <= r < mean.shape[0] and 0 <= c < mean.shape[1]:
                rows.append({
                    "checklist_id": ids[i], "tile": tile.filename,
                    "lidar_height_mean": float(mean[r, c]), "lidar_height_p95": float(p95[r, c]),
                    "lidar_height_std": float(std[r, c]), "lidar_cover": float(cover[r, c]),
                    "lidar_gap": float(1.0 - cover[r, c]),
                })
        if k % 25 == 0:
            print(f"  {k}/{len(tiles)} tiles, {len(rows):,} checklist rows", flush=True)

    frame = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.out, index=False)
    print(f"wrote {args.out}: {len(frame):,} checklist rows, {frame.checklist_id.nunique():,} checklists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
