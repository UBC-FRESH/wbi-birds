"""RBNU AF scale sweep with year-matched SCANFI v2 neighbourhood metrics.

Each checklist is paired with the SCANFI time step nearest its observation year.
Aspatial terms stay the kNN product used by the estate; the neighbourhood terms are
recomputed from the matched SCANFI year at 30 m.
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from pyproj import Transformer

ROOT = Path("/srv/shared-data/gep/wbi-birds")
sys.path.insert(0, str(ROOT / "reference/wbi-main/scripts"))
from fit_composition_probe import build
from scanfi_rbnu_scale import evaluate, metrics, RADII, NAMES, MAXR

SC = Path("/srv/shared-data/gep/jupyterhub16-projects/clews-c2070-fresh/data/raw/scanfi/v2")
TS = Path("/srv/shared-data/gep/wbi-birds/fvsbc-work/scanfi-ts")

# Years we can pair. 2025 is the tracked annex layer; other years are downloaded
# into fvsbc-work/scanfi-ts.
def _ready(a: Path, b: Path) -> bool:
    # aria2 keeps a .aria2 control file until the download is complete; the
    # preallocated file already has its full apparent size while in flight.
    if not (a.exists() and b.exists()):
        return False
    if Path(str(a) + ".aria2").exists() or Path(str(b) + ".aria2").exists():
        return False
    return a.stat().st_size > 5.0e9 and b.stat().st_size > 6.0e9


LAYERS = {}
for yr in (2010, 2015, 2020):
    a = TS / f"SCANFI_age_median_{yr}_v2_20260119.tif"
    b = TS / f"SCANFI_att_biomass_{yr}_v2_20260119.tif"
    if _ready(a, b):
        LAYERS[yr] = (a, b)
LAYERS[2025] = (SC / "SCANFI_age_median_2025_v2_20260119.tif",
               SC / "SCANFI_att_biomass_2025_v2_20260119.tif")


def nearest_year(y: int) -> int:
    return min(LAYERS, key=lambda k: abs(k - y))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    min_year = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    max_year = int(sys.argv[3]) if len(sys.argv) > 3 else 9999

    frame = build()
    samples = np.load(ROOT / "campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz",
                      allow_pickle=True)
    frame = frame.merge(pd.DataFrame({
        "event": samples["checklist_id"].astype(str),
        "lat": samples["latitude"],
        "lon": samples["longitude"],
        "year": samples["year"],
    }), on="event", how="inner")
    if min_year:
        frame = frame[frame.year >= min_year]
    if max_year < 9999:
        frame = frame[frame.year <= max_year]
    print("year window", min_year, max_year, "rows", len(frame), flush=True)
    frame = frame.dropna(subset=["rebnut", "soft_vol", "hard_vol", "age",
                                 "duration", "distance", "observers", "lat", "lon"])
    frame["log_soft"] = np.log1p(frame.soft_vol)
    frame["log_hard"] = np.log1p(frame.hard_vol)
    frame["year_c"] = (frame.year - frame.year.mean()) / max(frame.year.std(), 1e-9)
    frame = frame.sample(n=min(n, len(frame)), random_state=42)
    frame["sc_year"] = frame.year.map(nearest_year)
    print("sc year counts", frame.sc_year.value_counts().to_dict(), flush=True)

    recs, idxs = [], []
    t0 = time.time()
    age25_p, bio25_p = LAYERS[2025]
    with rasterio.open(age25_p) as a25, rasterio.open(bio25_p) as b25:
        for yr, grp in frame.groupby("sc_year"):
            age_p, bio_p = LAYERS[yr]
            print("reading", yr, "for", len(grp), "rows", flush=True)
            with rasterio.open(age_p) as a, rasterio.open(bio_p) as b:
                tr = Transformer.from_crs("EPSG:4326", a.crs, always_xy=True)
                xs, ys = tr.transform(grp.lon.to_numpy(), grp.lat.to_numpy())
                cols = np.floor((xs - a.transform.c) / a.transform.a).astype(int)
                rows = np.floor((ys - a.transform.f) / a.transform.e).astype(int)
                ok = 0
                for idx, r, c in zip(grp.index, rows, cols):
                    if r < MAXR or c < MAXR or r >= a.height - MAXR or c >= a.width - MAXR:
                        continue
                    w = Window(c - MAXR, r - MAXR, 2 * MAXR + 1, 2 * MAXR + 1)
                    age = a.read(1, window=w)
                    bio = b.read(1, window=w)
                    m = metrics(age, bio, r, c)
                    if m is None:
                        continue
                    total = float(bio[MAXR, MAXR])
                    agec = float(age[MAXR, MAXR])
                    m.update({"sc_biomass": total, "sc_age": agec})
                    # Same-row 2025 comparison, so the effect of matching can be
                    # separated from sampling and fold differences.
                    if yr == 2025:
                        m25 = {k: v for k, v in m.items()}
                    else:
                        age25 = a25.read(1, window=w)
                        bio25 = b25.read(1, window=w)
                        m25 = metrics(age25, bio25, r, c)
                        m25.update({"sc_biomass": float(bio25[MAXR, MAXR]),
                                    "sc_age": float(age25[MAXR, MAXR])})
                    for k, v in m25.items():
                        m[k + "_2025"] = v
                    recs.append(m)
                    idxs.append(idx)
                    ok += 1
                    if ok % 1000 == 0:
                        print(" ", yr, ok, round(time.time() - t0), flush=True)
                print(" ", yr, "kept", ok, flush=True)

    md = pd.DataFrame(recs, index=idxs)
    frame = frame.join(md)
    frame["sc_log_bio"] = np.log1p(frame.sc_biomass)
    frame.to_csv(ROOT / "fvsbc-work/rbnu-yearmatch-frame.csv", index=False)
    print("scanfi rows", len(md), "of", len(frame), flush=True)

    yt = " + year_c" if os.environ.get("YEAR_TERM") == "1" else ""
    base = "log_soft + log_hard + age" + yt
    scbase = "sc_log_bio + sc_age" + yt
    res = []
    aic, cv = evaluate(frame, base)
    res.append(("aspatial-knn", aic, cv))
    print("aspatial-knn", round(aic, 1), round(cv, 5), flush=True)
    scframe = frame.dropna(subset=["sc_log_bio", "sc_age"])
    aic, cv = evaluate(scframe, scbase)
    res.append(("aspatial-scanfi", aic, cv))
    print("aspatial-scanfi", round(aic, 1), round(cv, 5), flush=True)
    for r in RADII:
        nme = NAMES[r]
        formula = f"{base} + forest_{nme} + edge_{nme} + early_{nme}"
        aic, cv = evaluate(frame, formula)
        res.append((nme, aic, cv))
        print(nme, round(aic, 1), round(cv, 5), flush=True)
    for r in RADII:
        nme = NAMES[r]
        formula = f"{scbase} + forest_{nme} + edge_{nme} + early_{nme}"
        aic, cv = evaluate(scframe, formula)
        res.append(("scanfi-" + nme, aic, cv))
        print("scanfi-" + nme, round(aic, 1), round(cv, 5), flush=True)

    out = ROOT / "fvsbc-work/rbnu-yearmatch-sweep.csv"
    pd.DataFrame(res, columns=["scale", "aic", "cv_per_row"]).to_csv(out, index=False)
    print("wrote", out, flush=True)
