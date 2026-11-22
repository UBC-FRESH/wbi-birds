"""Build the LiDAR tile index for a bbox and join checklists to tiles.

Writes a TSV: checklists, x0, x1, y0, y1, filename, s3Url, demUrl

    python scripts/lidar_tile_index.py --bbox -123.0,54.1,-120.0,56.34 --out lidar/tsa41-tiles.tsv
"""
from __future__ import annotations

import argparse
import json
import subprocess
import urllib.parse
from pathlib import Path

import numpy as np

INDEX = "https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/LiDAR_BC_S3_Public/FeatureServer/1/query"
SAMPLES = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz")
PAGE = 1000


def fetch(offset: int, bbox: str) -> dict:
    params = {
        "where": "1=1", "geometry": bbox, "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outFields": "filename,s3Url", "returnGeometry": "true",
        "outSR": "4326", "resultOffset": str(offset), "resultRecordCount": str(PAGE), "f": "json",
    }
    url = INDEX + "?" + urllib.parse.urlencode(params)
    out = subprocess.run(["curl", "-s", "--max-time", "180", url], capture_output=True, text=True).stdout
    return json.loads(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    samples = np.load(SAMPLES, allow_pickle=True)
    lat = samples["latitude"]
    lon = samples["longitude"]
    rows, offset, tiles = [], 0, 0
    while True:
        data = fetch(offset, args.bbox)
        feats = data.get("features", [])
        if not feats:
            break
        for f in feats:
            ring = f["geometry"]["rings"][0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            n = int(((lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)).sum())
            name = f["attributes"]["filename"]
            s3 = f["attributes"]["s3Url"]
            dem = s3.replace("/dsm/", "/dem/").replace("_dsm.tif", ".tif")
            rows.append((n, x0, x1, y0, y1, name, s3, dem))
        tiles += len(feats)
        offset += len(feats)
        print(f"fetched {tiles:,} tiles", flush=True)
        if not data.get("exceededTransferLimit") and len(feats) < PAGE:
            break
    rows.sort(key=lambda r: -r[0])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join("\t".join(str(v) for v in r) for r in rows) + "\n")
    total = sum(r[0] for r in rows)
    print(f"{len(rows):,} tiles; checklists inside tiles: {total:,}; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
