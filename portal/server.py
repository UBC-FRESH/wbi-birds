"""Static portal server + high-resolution block API for the wbi-birds explorer.

The overview GeoJSON is decimated, but zooming in fetches exact block geometry for the
current viewport from the femic checkpoint (EPSG:3005), transformed to EPSG:4326.

    python server.py --host 0.0.0.0 --port 8132
"""
from __future__ import annotations

import argparse
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pyproj import Transformer
from shapely import wkb
from shapely.geometry import box
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree

UI = Path(__file__).resolve().parent / "ui"
CAMPAIGNS = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11")
CHECKPOINTS = {
    "41": "/tmp/opencode/rebuild/tsa41/data/vri_vclr1p_checkpoint7.feather",
    "16": "/tmp/opencode/rebuild/tsa16/data/vri_vclr1p_checkpoint7.feather",
    "40": "/tmp/opencode/rebuild/tsa40/data/vri_vclr1p_checkpoint7.feather",
    "08": "/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa08-instance/data/ria_vri_vclr1p_checkpoint7.feather",
    "24": "/tmp/opencode/tsa24-checkpoint7.feather",
}
THRESHOLDS = {"41": 50, "40": 50, "24": 50, "16": 67, "08": 93}
TO_WGS = Transformer.from_crs("EPSG:3005", "EPSG:4326", always_xy=True)
TO_ALBERS = Transformer.from_crs("EPSG:4326", "EPSG:3005", always_xy=True)

app = FastAPI(title="WBI Birds portal", docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)

_cache: dict[str, dict] = {}
_lock = threading.Lock()


def load_tsa(tsa: str) -> dict:
    """Load geometry and attributes for one TSA (cached). Accepts ``41`` or ``tsa41``."""
    tsa = tsa.lower().removeprefix("tsa")
    if tsa in _cache:
        return _cache[tsa]
    if tsa not in CHECKPOINTS:
        raise HTTPException(status_code=404, detail="unknown TSA")
    with _lock:
        if tsa in _cache:
            return _cache[tsa]
        frame = pd.read_feather(CHECKPOINTS[tsa], columns=["geometry", "POLYGON_AREA", "PROJ_AGE_1", "thlb_raw"])
        geoms = [wkb.loads(g) for g in frame["geometry"].to_numpy()]
        area = frame["POLYGON_AREA"].to_numpy(float)
        if np.nanmedian(area) > 100:
            area = area / 1e4
        age = np.nan_to_num(frame["PROJ_AGE_1"].to_numpy(float), nan=0.0)
        managed = frame["thlb_raw"].to_numpy(float) >= THRESHOLDS[tsa]
        schedule: dict[int, int] = {}
        prime = CAMPAIGNS / f"prime/tsa{tsa}-prime.csv"
        if prime.exists():
            sched = pd.read_csv(prime)
            schedule = dict(zip(sched.block_id.astype(int), sched.offset.astype(int)))
        payload = {"geoms": geoms, "tree": STRtree(geoms), "area": area, "age": age,
                   "managed": managed, "schedule": schedule}
        _cache[tsa] = payload
        return payload


def ring_coords(ring) -> list[list[float]]:
    xs, ys = TO_WGS.transform([c[0] for c in ring.coords], [c[1] for c in ring.coords])
    return [[round(x, 6), round(y, 6)] for x, y in zip(xs, ys)]


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


@app.get("/api/manifest")
def manifest() -> JSONResponse:
    path = UI / "data" / "manifest.json"
    if not path.exists():
        return JSONResponse({"error": "data contract missing"}, status_code=503)
    return JSONResponse(json.loads(path.read_text()))


@app.get("/api/blocks/{tsa}")
def blocks(tsa: str, bbox: str = Query(..., description="minx,miny,maxx,maxy in EPSG:4326"),
           limit: int = Query(4000, ge=1, le=12000)) -> JSONResponse:
    """Return exact block geometry intersecting the viewport."""
    data = load_tsa(tsa)
    try:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy") from exc
    ax0, ay0 = TO_ALBERS.transform(minx, miny)
    ax1, ay1 = TO_ALBERS.transform(maxx, maxy)
    query = box(min(ax0, ax1), min(ay0, ay1), max(ax0, ax1), max(ay0, ay1))
    hits = data["tree"].query(query)
    if len(hits) > limit:
        order = np.argsort(-data["area"][hits])[:limit]
        hits = hits[order]
    features = []
    for i in hits:
        geom = data["geoms"][i]
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        coordinates = []
        for poly in polys:
            poly = orient(poly, 1.0)
            coordinates.append([ring_coords(poly.exterior), *[ring_coords(r) for r in poly.interiors]])
        geometry = ({"type": "Polygon", "coordinates": coordinates[0]} if len(coordinates) == 1
                    else {"type": "MultiPolygon", "coordinates": coordinates})
        features.append({
            "type": "Feature",
            "properties": {"b": int(i), "m": int(data["managed"][i]), "a": int(data["age"][i]),
                           "y": int(data["schedule"].get(int(i), -1))},
            "geometry": geometry,
        })
    return JSONResponse({"type": "FeatureCollection", "features": features})


app.mount("/", StaticFiles(directory=UI, html=True), name="ui")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8132)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
