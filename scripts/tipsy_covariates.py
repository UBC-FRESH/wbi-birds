"""Join TIPSY stand-level structural curves to checklists by block, AU, and age.

Outputs a parquet with four forward-predictable covariates per checklist:
TIPSY top height, crown cover, DBHq, and TPH, interpolated at the block's inventory age.
Column names mirror the LiDAR table so the AF comparison can use either source.

    python scripts/tipsy_covariates.py --dataset <compiled> --checkpoint <feather> \
      --tipsy <tipsy_curves.csv> --out <parquet>
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import wkb
from shapely.strtree import STRtree

SAMPLES = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz")
TO_ALBERS = Transformer.from_crs("EPSG:4326", "EPSG:3005", always_xy=True)
AU = re.compile(r"AU\((\d+)\)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--tipsy", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    tracks = pd.read_parquet(args.dataset / "tracks.parquet")
    au_of_track = {}
    for row in tracks.itertuples():
        match = AU.search(str(row.name))
        if match:
            au_of_track[int(row.track_id)] = int(match.group(1))

    fragments = pd.read_parquet(args.dataset / "fragments.parquet", columns=["block_id", "track_id"])
    block_track = dict(zip(fragments.block_id.astype(int), fragments.track_id.astype(int)))

    checkpoint = pd.read_feather(args.checkpoint, columns=["geometry", "PROJ_AGE_1", "POLYGON_AREA"])
    geoms = [wkb.loads(g) for g in checkpoint.geometry.to_numpy()]
    ages = checkpoint.PROJ_AGE_1.to_numpy(float)
    tree = STRtree(geoms)

    tipsy = pd.read_csv(args.tipsy)
    by_au = {}
    for au, group in tipsy.groupby("AU"):
        group = group.sort_values("Age")
        by_au[int(au)] = {col: group[col].to_numpy(float) for col in ("Age", "Height", "CrownCover", "DBHq", "TPH")}

    samples = np.load(SAMPLES, allow_pickle=True)
    ids = samples["checklist_id"].astype(str)
    x, y = TO_ALBERS.transform(samples["longitude"].astype(float), samples["latitude"].astype(float))

    from shapely import points as shapely_points

    coords = shapely_points(np.column_stack([x, y]))
    hits = tree.query(coords)  # shape (2, n): input index, tree index
    matches: dict[int, list[int]] = {}
    for input_index, block_index in zip(hits[0], hits[1]):
        matches.setdefault(int(input_index), []).append(int(block_index))
    rows = []
    for i in range(len(ids)):
        blocks = matches.get(i)
        if not blocks:
            continue
        b = int(blocks[0])
        track = block_track.get(b)
        au = au_of_track.get(int(track)) if track is not None else None
        tipsy_au = int(au) - 4_080_000 if au is not None else None
        curves = by_au.get(tipsy_au) if tipsy_au is not None else None
        if curves is None:
            continue
        age = float(ages[b]) if np.isfinite(ages[b]) else np.nan
        if not np.isfinite(age):
            continue
        def at(col):
            return float(np.interp(age, curves["Age"], curves[col]))
        rows.append({
            "checklist_id": ids[i],
            "tipsy_au": int(tipsy_au),
            "lidar_height_mean": at("Height"),
            "lidar_height_p95": at("Height"),
            "lidar_height_std": 0.0,
            "lidar_cover": at("CrownCover") / 100.0,
            "tipsy_dbhq": at("DBHq"),
            "tipsy_tph": at("TPH"),
        })
    frame = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.out, index=False)
    print(f"wrote {args.out}: {len(frame):,} checklists, {frame.tipsy_au.nunique()} AUs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
