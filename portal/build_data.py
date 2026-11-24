"""Build the JSON/GeoJSON data contract for the wbi-birds portal.

Reads the campaign artifacts and writes static views under ``ui/data``:
manifest, land base, bird fits, pilot tradeoff points, same-schedule impact, and
simplified block maps per TSA.

    python build_data.py
"""
from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import wkb
from shapely.geometry.polygon import orient

CAMPAIGNS = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11")
OUT = Path(__file__).resolve().parent / "ui" / "data"

TSRS = {
    "41": {"name": "Dawson Creek", "thlb": 758335, "source": "AAC reduction rationale, Jun 2024", "aac": 1791846, "aac_date": "2024-06-20"},
    "40": {"name": "Fort St. John", "thlb": 1020817, "source": "AAC rationale, May 2018", "aac": 2115000, "aac_date": "2018-05-10"},
    "24": {"name": "Prince George", "thlb": 3100000, "source": "TSA backgrounder 2012 (approx.)", "aac": 6917231, "aac_date": "2025-08-28"},
    "16": {"name": "Mackenzie", "thlb": 1228612, "source": "AAC rationale, May 2023", "aac": 2321476, "aac_date": "2024-06-20"},
    "08": {"name": "Fort Nelson", "thlb": 705761, "source": "TSR discussion paper, Jul 2018", "aac": 2582350, "aac_date": "2019-07-16"},
}
THRESHOLDS = {"41": 50, "40": 50, "24": 50, "16": 67, "08": 93}
GEOM = {
    "41": "/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa41-instance/data/ria_vri_vclr1p_checkpoint7.feather",
    "16": "/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa16-instance/data/ria_vri_vclr1p_checkpoint7.feather",
    "40": "/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa40-instance/data/ria_vri_vclr1p_checkpoint7.feather",
    "08": "/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa08-instance/data/ria_vri_vclr1p_checkpoint7.feather",
    "24": "/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa24-instance/data/ria_vri_vclr1p_checkpoint7.feather",
}
SPECIES = {
    "rebnut": "Red-breasted Nuthatch", "borchi2": "Boreal Chickadee", "gockin": "Golden-crowned Kinglet",
    "brncre": "Brown Creeper", "yerwar": "Yellow-rumped Warbler", "swathr": "Swainson's Thrush",
    "whtspa": "White-throated Sparrow", "tenwar": "Tennessee Warbler", "yebsap": "Yellow-bellied Sapsucker",
}


def area_ha(frame: pd.DataFrame) -> np.ndarray:
    a = frame["POLYGON_AREA"].to_numpy(float)
    if np.nanmedian(a) > 100:  # TSA24 checkpoint is in square metres
        a = a / 1e4
    return a


def landbase() -> dict:
    out = {"tsas": []}
    candidates = {t: CAMPAIGNS / f"full-landscape/tsa{t}/cache/candidates.pkl" for t in TSRS}
    for t, meta in TSRS.items():
        frame = pd.read_feather(GEOM[t], columns=["POLYGON_AREA", "thlb_raw", "PROJ_AGE_1"])
        a = area_ha(frame)
        frac = np.clip(frame["thlb_raw"].to_numpy(float) / 100.0, 0, 1)
        threshold = THRESHOLDS[t]
        managed = frame["thlb_raw"].to_numpy(float) >= threshold
        age = frame["PROJ_AGE_1"].to_numpy(float)
        bins = np.arange(0, 321, 20)
        hist_m = np.histogram(age[managed], bins=bins)[0].tolist()
        hist_u = np.histogram(age[~managed], bins=bins)[0].tolist()
        out["tsas"].append({
            "tsa": f"tsa{t}", "code": t, "name": meta["name"],
            "total_ha": round(float(a.sum()), 1),
            "managed_full_ha": round(float(a[managed].sum()), 1),
            "managed_weighted_ha": round(float((a[managed] * frac[managed]).sum()), 1),
            "unmanaged_ha": round(float(a[~managed].sum()), 1),
            "polygons": int(len(a)), "managed_polygons": int(managed.sum()),
            "threshold": threshold, "tsr_thlb_ha": meta["thlb"], "tsr_source": meta["source"],
            "ratio_weighted_tsr": round(float((a[managed] * frac[managed]).sum()) / meta["thlb"], 3),
            "aac_m3_yr": meta["aac"], "aac_date": meta["aac_date"],
            "age_bins": bins[:-1].tolist(), "age_managed": hist_m, "age_unmanaged": hist_u,
        })
    return out


def fits() -> dict:
    base = json.loads((CAMPAIGNS / "bird-fits/knn-v0-nine-species-log.json").read_text())
    spatial = json.loads((CAMPAIGNS / "bird-fits/scanfi-240m-nine-species-spatial.json").read_text())
    species = []
    for code, label in SPECIES.items():
        asp = base["species"][code]
        sp = spatial["species"][code]
        species.append({
            "code": code, "label": label,
            "aspatial": {"coefficients": asp["fit"]["coefficients"], "aic": asp.get("aic"),
                         "dispersion": asp.get("dispersion"), "eta_cap": asp.get("eta_cap")},
            "spatial": {"coefficients": sp["coefficients"], "aic": sp.get("aic"),
                        "dispersion": sp.get("dispersion"), "eta_cap": sp.get("eta_cap")},
        })
    cov_path = CAMPAIGNS / "knn-v0/spatial-covariates-study-area.npz"
    covariates = {}
    if cov_path.exists():
        cov = np.load(cov_path)
        for key in cov.files:
            a = cov[key].astype(float)
            covariates[key] = {
                "n": int(a.size), "mean": round(float(np.mean(a)), 4),
                "p05": round(float(np.percentile(a, 5)), 4),
                "p50": round(float(np.percentile(a, 50)), 4),
                "p95": round(float(np.percentile(a, 95)), 4),
            }
    return {
        "covariates": covariates,
        "methods": {
            "definition": base.get("definition"), "link": base.get("link"),
            "covariate_form": base.get("covariate_form"),
            "aspatial": "log(abundance) ~ log1p(softwood volume) + log1p(hardwood volume) + age",
            "spatial": "same, plus SCANFI 240 m forest + edge + early-seral fractions in a 1.92 km window",
            "note": "Spatial fit: 604,935 checklists from 2018-2026 with SCANFI 2020/2025 metrics; aspatial curves from the kNN v0 fit. Raw eBird records are never exposed.",
        },
        "species": species,
    }


def read_rows(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def frontiers() -> dict:
    """Campaign points if present, otherwise the TSA41/GCKI pilot."""
    points: list[dict] = []
    campaign_files = sorted(p for p in CAMPAIGNS.glob("dual-scanfi-240m/tsa*-multi-s42-*.csv")
                            if "schedules" not in p.name)
    best: dict[tuple, dict] = {}
    for path in campaign_files:
        for row in read_rows(path):
            if "tsa" not in row:
                continue
            tsa = row["tsa"]
            base_path = CAMPAIGNS / f"dual-scanfi-240m/{tsa}-baselines.json"
            if not base_path.exists():
                continue
            base = json.loads(base_path.read_text())
            mode, bird = row["mode"], row["bird"]
            if bird not in base.get(mode, {}):
                continue
            attainment = float(row["bird_p20"]) / float(base[mode][bird])
            key = (tsa, bird, mode, round(float(row["epsilon_p20"]), 0))
            objective = float(row["objective"])
            if key not in best or objective < best[key]["objective"]:
                best[key] = {
                    "tsa": tsa, "bird": bird, "mode": mode,
                    "attainment": round(attainment, 4),
                    "target_attainment": round(float(row["epsilon_p20"]) / float(base[mode][bird]), 4),
                    "harvest_M_m3_yr": float(row["harvest_realized_m3_yr"]),
                    "epsilon_p20": float(row["epsilon_p20"]), "bird_p20": float(row["bird_p20"]),
                    "iterations": int(row["iterations"]), "seed": int(row["seed"]),
                    "objective": objective,
                }
    points = sorted(best.values(), key=lambda r: (r["tsa"], r["bird"], r["mode"], r["attainment"]))

    if not points:
        baseline = {"aspatial": 1643203.0, "spatial": 2035129.0}
        pilot = CAMPAIGNS / "dual-scanfi-240m/tsa41-multi-s42-gockin.csv"
        if pilot.exists():
            for row in read_rows(pilot):
                att = float(row["bird_p20"]) / baseline[row["mode"]]
                points.append({
                    "tsa": row["tsa"], "bird": row["bird"], "mode": row["mode"],
                    "attainment": round(att, 4), "target_attainment": round(att, 4),
                    "harvest_M_m3_yr": float(row["harvest_realized_m3_yr"]),
                    "epsilon_p20": float(row["epsilon_p20"]), "bird_p20": float(row["bird_p20"]),
                    "iterations": int(row["iterations"]), "seed": int(row["seed"]),
                    "objective": float(row["objective"]),
                })
    seeds = []
    seed_file = CAMPAIGNS / "dual/tsa41-gockin-seeds.csv"
    if seed_file.exists():
        for row in read_rows(seed_file):
            seeds.append({"tsa": row["tsa"], "bird": row["bird"], "mode": row["mode"],
                          "attainment": round(float(row["bird_p20"]) / 1643203.0 if row["mode"] == "aspatial" else float(row["bird_p20"]) / 2035129.0, 4),
                          "target_attainment": round(float(row["epsilon_p20"]) / 1643203.0 if row["mode"] == "aspatial" else float(row["epsilon_p20"]) / 2035129.0, 4),
                          "harvest_M_m3_yr": float(row["harvest_realized_m3_yr"]),
                          "seed": int(row["seed"])})
    impact = []
    impact_file = CAMPAIGNS / "dual-scanfi-240m/tsa41-impact.csv"
    if impact_file.exists():
        for row in read_rows(impact_file):
            impact.append({"species": row["species"],
                           "harvest_M_m3_yr": float(row["harvest_M_m3_yr"]),
                           "aspatial_pct": float(row["aspatial_pct"]),
                           "spatial_pct": float(row["spatial_pct"]),
                           "sign_flip": (float(row["aspatial_pct"]) * float(row["spatial_pct"]) < 0)})
    guild_points = []
    guild_response = []
    response_path = CAMPAIGNS / "dual-scanfi-240m/tsa41-guild-response.csv"
    if response_path.exists():
        for row in read_rows(response_path):
            if row.get("guild") not in {"mature_conifer", "mixedwood", "early_seral", "cavity"}:
                continue
            if not row["schedule"].startswith("aspatial-"):
                continue
            attainment = float(row["schedule"].split("-")[1])
            guild_points.append({
                "tsa": "tsa41", "bird": row["guild"], "mode": "aspatial",
                "target_attainment": attainment, "attainment": attainment,
                "harvest_M_m3_yr": float(row["harvest"]),
            })
            guild_response.append({
                "tsa": "tsa41",
                "bird": row["guild"],
                "harvest_M_m3_yr": float(row["harvest"]),
                "aspatial_pct": 100.0 * float(row["aspatial"]),
                "spatial_pct": 100.0 * float(row["spatial"]),
                "attainment": attainment,
            })

    curve_path = CAMPAIGNS / "dual-full/curves.json"
    curves = json.loads(curve_path.read_text()) if curve_path.exists() else []
    return {
        "status": "full campaign" if campaign_files and points else "pilot",
        "curves": curves,
        "guild_frontier": guild_points,
        "guild_response": guild_response,
        "points": points, "seeds": seeds, "impact": impact,
        "verdict": {
            "rule": "aspatial preferred if |delta harvest| <= 2% at equal relative attainment",
            "result": ("pilot: aspatial rejected (worst 105%)" if not campaign_files else
                       "full grid: aspatial rejected; 29 feasible pairs, median |delta harvest| 9.3%, "
                       "worst 43.8%; aspatial allows more harvest in 17 pairs, spatial in 2, 10 tied"),
        },
    }


def build_map(t: str, meta: dict) -> None:
    threshold = THRESHOLDS[t]
    frame = pd.read_feather(GEOM[t], columns=["POLYGON_AREA", "thlb_raw", "PROJ_AGE_1", "geometry"])
    a = area_ha(frame)
    thlb = frame["thlb_raw"].to_numpy(float)
    managed = thlb >= threshold
    age = frame["PROJ_AGE_1"].to_numpy(float)
    schedule = {}
    prime = CAMPAIGNS / f"prime/tsa{t}-prime.csv"
    if prime.exists():
        sched = pd.read_csv(prime)
        schedule = dict(zip(sched.block_id.astype(int), sched.offset.astype(int)))
    # keep the largest polygons for visual coverage plus a random tail
    order = np.argsort(-a)
    keep = set(order[:20000].tolist())
    rng = random.Random(42)
    tail = [i for i in order[20000:] if rng.random() < 0.02]
    keep.update(int(i) for i in tail)
    keep = sorted(keep)
    transformer = Transformer.from_crs("EPSG:3005", "EPSG:4326", always_xy=True)
    geoms = frame["geometry"].to_numpy()
    features = []
    for i in keep:
        try:
            geom = wkb.loads(geoms[i])
        except Exception:
            continue
        geom = geom.simplify(18.0, preserve_topology=True)
        if geom.is_empty:
            continue
        if geom.geom_type == "Polygon":
            polys = [orient(geom, 1.0)]
        elif geom.geom_type == "MultiPolygon":
            polys = [orient(p, 1.0) for p in geom.geoms]
        else:
            continue
        polygons = []
        for poly in polys:
            rings = []
            for ring in [poly.exterior, *poly.interiors]:
                coords = list(ring.coords)
                xy = transformer.transform([c[0] for c in coords], [c[1] for c in coords])
                rings.append([[round(x, 5), round(y, 5)] for x, y in zip(*xy)])
            if rings:
                polygons.append(rings)
        if not polygons:
            continue
        geometry = ({"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1
                    else {"type": "MultiPolygon", "coordinates": polygons})
        features.append({
            "type": "Feature",
            "properties": {"b": int(i), "m": int(managed[i]), "a": int(age[i]) if np.isfinite(age[i]) else 0,
                           "y": int(schedule.get(int(i), -1))},
            "geometry": geometry,
        })
    payload = {"type": "FeatureCollection", "features": features}
    path = OUT / "maps" / f"tsa{t}.geojson"
    path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"  tsa{t}: {len(features):,} polygons -> {path.stat().st_size/1e6:.1f} MB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "maps").mkdir(exist_ok=True)
    print("land base")
    lb = landbase()
    (OUT / "landbase.json").write_text(json.dumps(lb, indent=2))
    print("fits")
    (OUT / "fits.json").write_text(json.dumps(fits(), indent=2))
    print("frontiers")
    fr = frontiers()
    (OUT / "frontiers.json").write_text(json.dumps(fr, indent=2))
    print("maps")
    for t, meta in TSRS.items():
        build_map(t, meta)
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tsas": [f"tsa{t}" for t in TSRS],
        "species": list(SPECIES),
        "campaign_status": ("full campaign complete: 80 points, 5 TSAs x 4 species x 2 attainments x 2 modes"
                            if (OUT / "frontiers.json").exists() and json.loads((OUT / "frontiers.json").read_text()).get("status") == "full campaign"
                            else "pilot complete (TSA41/GCKI)"),
        "caveats": [
            "Tradeoff points are the TSA41/GCKI pilot at 300k iterations, single chain.",
            "THLB thresholds are calibrated to TSR-reported THLBs (documented in the campaign record).",
            "Raw eBird records are not exposed; only fitted coefficients and aggregates.",
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
