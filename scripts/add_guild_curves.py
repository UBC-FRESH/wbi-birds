"""Add linear guild abundance accounts to a compiled dataset.

A guild is a sum of member species' bird curves per track, consistent with the
manuscript's linear guild indicators. Adds ``feature.Bird.<guild>`` feature rows and
curves; existing files are backed up.

    python scripts/add_guild_curves.py --dataset <compiled> --guild mature_conifer
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

GUILDS = {
    "mature_conifer": ("rebnut", "borchi2", "gockin", "brncre"),
    "mixedwood": ("yerwar", "swathr"),
    "early_seral": ("whtspa", "tenwar"),
    "cavity": ("yebsap",),
}
GRID = np.arange(0, 301)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--guild", nargs="+", default=list(GUILDS))
    args = parser.parse_args()

    features = pd.read_parquet(args.dataset / "features.parquet")
    curves = pd.read_parquet(args.dataset / "curves.parquet")
    next_id = int(curves.curve_id.max()) + 1
    new_curves = []
    new_features = []
    for guild in args.guild:
        members = GUILDS[guild]
        label = f"feature.Bird.{guild}"
        if (features.label == label).any():
            print(f"{guild}: already present")
            continue
        by_track = features[features.label.isin([f"feature.Bird.{m}" for m in members])]
        added = 0
        for track, rows in by_track.groupby("track_id"):
            present = set(rows.label)
            if any(f"feature.Bird.{m}" not in present for m in members):
                continue
            total = np.zeros_like(GRID, dtype=float)
            for row in rows.itertuples():
                curve = curves[curves.curve_id == row.curve_id].sort_values("x")
                total += np.interp(GRID, curve.x.to_numpy(float), curve.y.to_numpy(float),
                                   left=0.0, right=float(curve.y.iloc[-1]))
            new_curves.append(pd.DataFrame({"curve_id": next_id, "x": GRID, "y": total}))
            new_features.append({"track_id": int(track), "label": label, "curve_id": next_id})
            next_id += 1
            added += 1
        print(f"{guild}: {added} tracks")

    if new_curves:
        backup = args.dataset / "compiled-guild-backup"
        backup.mkdir(exist_ok=True)
        for name in ("features.parquet", "curves.parquet"):
            target = backup / name
            if not target.exists():
                shutil.copyfile(args.dataset / name, target)
        curves = pd.concat([curves, *new_curves], ignore_index=True)
        features = pd.concat([features, pd.DataFrame(new_features)], ignore_index=True)
        curves.to_parquet(args.dataset / "curves.parquet", index=False)
        features.to_parquet(args.dataset / "features.parquet", index=False)
        print(f"wrote {len(new_features)} guild feature rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
