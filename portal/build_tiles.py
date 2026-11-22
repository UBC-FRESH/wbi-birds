"""Build directory vector tiles (MVT) per TSA for the portal map.

Full-resolution geometry is ingested as GeoJSONSeq; tippecanoe handles per-zoom
generalisation, so no fixed simplify tolerance is applied to the source.

    python build_tiles.py            # all TSAs
    python build_tiles.py 41 24      # selected
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import wkb
from shapely.geometry.polygon import orient

CAMPAIGNS = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11")
OUT = Path(__file__).resolve().parent / "ui"
TIPPECANOE = Path("/tmp/opencode/tippecanoe/tippecanoe")
CHECKPOINTS = {
    "41": "/tmp/opencode/rebuild/tsa41/data/vri_vclr1p_checkpoint7.feather",
    "16": "/tmp/opencode/rebuild/tsa16/data/vri_vclr1p_checkpoint7.feather",
    "40": "/tmp/opencode/rebuild/tsa40/data/vri_vclr1p_checkpoint7.feather",
    "08": "/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa08-instance/data/ria_vri_vclr1p_checkpoint7.feather",
    "24": "/tmp/opencode/tsa24-checkpoint7.feather",
}
THRESHOLDS = {"41": 50, "40": 50, "24": 50, "16": 67, "08": 93}
TO_WGS = Transformer.from_crs("EPSG:3005", "EPSG:4326", always_xy=True)


def build(tsa: str) -> dict:
    frame = pd.read_feather(CHECKPOINTS[tsa], columns=["geometry", "POLYGON_AREA", "PROJ_AGE_1", "thlb_raw"])
    area = frame["POLYGON_AREA"].to_numpy(float)
    if np.nanmedian(area) > 100:
        area = area / 1e4
    age = np.nan_to_num(frame["PROJ_AGE_1"].to_numpy(float), nan=0.0)
    managed = frame["thlb_raw"].to_numpy(float) >= THRESHOLDS[tsa]
    schedule = {}
    prime = CAMPAIGNS / f"prime/tsa{tsa}-prime.csv"
    if prime.exists():
        sched = pd.read_csv(prime)
        schedule = dict(zip(sched.block_id.astype(int), sched.offset.astype(int)))
    geoms = frame["geometry"].to_numpy()

    seq = Path(f"/tmp/opencode/tiles-tsa{tsa}.geojsonl")
    minx, miny, maxx, maxy = 180.0, 90.0, -180.0, -90.0
    with seq.open("w") as handle:
        for i, raw in enumerate(geoms):
            try:
                geom = wkb.loads(raw)
            except Exception:
                continue
            polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
            coordinates = []
            for poly in polys:
                poly = orient(poly, 1.0)
                rings = []
                for ring in [poly.exterior, *poly.interiors]:
                    xs, ys = TO_WGS.transform([c[0] for c in ring.coords], [c[1] for c in ring.coords])
                    rings.append([[round(x, 7), round(y, 7)] for x, y in zip(xs, ys)])
                    for x, y in zip(xs, ys):
                        if x < minx: minx = x
                        if x > maxx: maxx = x
                        if y < miny: miny = y
                        if y > maxy: maxy = y
                coordinates.append(rings)
            geometry = ({"type": "Polygon", "coordinates": coordinates[0]} if len(coordinates) == 1
                        else {"type": "MultiPolygon", "coordinates": coordinates})
            feature = {"type": "Feature",
                       "properties": {"b": int(i), "m": int(managed[i]), "a": int(age[i]),
                                      "y": int(schedule.get(int(i), -1))},
                       "geometry": geometry}
            handle.write(json.dumps(feature, separators=(",", ":")) + "\n")
    print(f"  tsa{tsa}: wrote {seq.stat().st_size/1e6:.0f} MB GeoJSONSeq", flush=True)

    out = OUT / "tiles" / f"tsa{tsa}"
    if out.exists():
        shutil.rmtree(out)
    command = [str(TIPPECANOE), "-e", str(out), "-l", "blocks",
               "-Z5", "-z14", "--full-detail=14", "--no-tile-compression",
               "--drop-densest-as-needed", "--simplification=1", "--buffer=64", "--force", "--quiet",
               str(seq)]
    subprocess.run(command, check=True)
    seq.unlink(missing_ok=True)
    tiles = sum(1 for _ in out.rglob("*.pbf"))
    print(f"  tsa{tsa}: {tiles:,} tiles", flush=True)
    return {"bbox": [round(minx, 5), round(miny, 5), round(maxx, 5), round(maxy, 5)]}


def main() -> None:
    wanted = sys.argv[1:] or list(CHECKPOINTS)
    (OUT / "tiles").mkdir(parents=True, exist_ok=True)
    bounds = {}
    path = OUT / "data" / "tsa_bounds.json"
    if path.exists():
        bounds = json.loads(path.read_text())
    for tsa in wanted:
        print(f"tsa{tsa}", flush=True)
        try:
            bounds[f"tsa{tsa}"] = build(tsa)
            path.write_text(json.dumps(bounds, indent=2))
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED tsa{tsa}: {exc}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
