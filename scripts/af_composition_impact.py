"""Compare current and composition-aware AFs on one schedule (TSA41 prime).

Evaluates four predictions per block at period 20 -- current aspatial, current spatial,
composition aspatial, composition spatial -- for the no-harvest and harvested states,
and reports the percentage change each model implies.

    python scripts/af_composition_impact.py --dataset <compiled> --prime <schedule.csv>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_model20 import SpatialBird20, YEAR, MAX_AGE  # noqa: E402

HARD = {"AT", "AC", "ACT", "EP"}
PINE = {"PL", "PLI"}
SPRUCE = {"SW", "SX", "SE", "SB"}
FIR = {"BL"}
CEDAR = {"CW", "YC", "HW"}
ASPEN = {"AT"}
BIRCH = {"AC", "ACT"}


def track_curves(dataset: Path) -> dict[int, dict[str, np.ndarray]]:
    feats = pd.read_parquet(dataset / "features.parquet")
    curves = pd.read_parquet(dataset / "curves.parquet")
    grid = np.arange(0, MAX_AGE + 1)
    out: dict[int, dict[str, np.ndarray]] = {}
    for row in feats.itertuples():
        parts = str(row.label).split(".")
        if len(parts) != 4 or parts[0] != "feature" or parts[1] != "Yield" or parts[3] == "Total":
            continue
        curve = curves[curves.curve_id == row.curve_id].sort_values("x")
        values = np.interp(grid, curve.x.to_numpy(float), curve.y.to_numpy(float),
                           left=0.0, right=float(curve.y.iloc[-1]))
        out.setdefault(int(row.track_id), {})[parts[3]] = values
    return out


def composition(track_yields: dict[str, np.ndarray], age: int) -> dict[str, float]:
    species = {code: float(values[age]) for code, values in track_yields.items()}
    total = float(sum(species.values()))
    if total <= 0:
        return {"total": 0.0, "soft": 0.0, "hard": 0.0,
                "pine": 0.0, "spruce": 0.0, "fir": 0.0, "cedar": 0.0, "aspen": 0.0, "birch": 0.0}
    def share(codes):
        return float(sum(species.get(code, 0.0) for code in codes) / total)
    hard = float(sum(species.get(code, 0.0) for code in HARD))
    return {"total": total, "soft": total - hard, "hard": hard,
            "pine": share(PINE), "spruce": share(SPRUCE), "fir": share(FIR),
            "cedar": share(CEDAR), "aspen": share(ASPEN), "birch": share(BIRCH)}


def eta_current_aspatial(coef, age, soft, hard):
    eta = coef["intercept"] + coef["softwood"] * np.log1p(soft) + coef["hardwood"] * np.log1p(hard) + coef["age"] * age
    return eta


def eta_current_spatial(coef, age, soft, hard, forest, edge, early):
    return (coef["intercept"] + coef["log1p_softwood"] * np.log1p(soft) + coef["log1p_hardwood"] * np.log1p(hard)
            + coef["age"] * age + coef["pct_forest_1km"] * forest + coef["edge_1km"] * edge
            + coef["pct_early_500m"] * early)


def eta_composition(coef, age, soft, hard, comp, forest=None, edge=None, early=None):
    eta = (coef["intercept"] + coef["log_soft"] * np.log1p(soft) + coef["log_hard"] * np.log1p(hard)
           + coef["age"] * age)
    for key in ("pine", "spruce", "fir", "cedar", "aspen", "birch"):
        eta += coef.get(key, 0.0) * comp[key]
    if "log_age:pine" in coef:
        for key in ("pine", "aspen", "cedar"):
            eta += coef.get(f"log_age:{key}", 0.0) * np.log1p(age) * comp[key]
    else:
        for key in ("pine", "aspen", "cedar"):
            eta += coef.get(f"age:{key}", 0.0) * age * comp[key]
    if forest is not None:
        eta += coef.get("pct_forest_1km", 0.0) * forest + coef.get("edge_1km", 0.0) * edge + coef.get("pct_early_500m", 0.0) * early
    return eta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--prime", type=Path, required=True)
    parser.add_argument("--fits", type=Path, default=Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/bird-fits"))
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--birds", nargs="+", default=["rebnut", "borchi2", "gockin", "brncre"])
    args = parser.parse_args()

    fragments = pd.read_parquet(args.dataset / "fragments.parquet")
    area = fragments.area_ha.to_numpy(float)
    track = fragments.track_id.to_numpy(int)
    age0 = fragments.age.to_numpy(float)
    schedule = pd.read_csv(args.prime)
    cut = dict(zip(schedule.block_id.astype(int), schedule.offset.astype(int)))
    years = np.array([cut.get(int(i), None) for i in range(len(fragments))], dtype=object)
    age_harvest = np.array([max(YEAR - y, 0) if y is not None and y <= YEAR else min(age0[i] + YEAR, MAX_AGE)
                            for i, y in enumerate(years)], dtype=float)
    age_no = np.minimum(age0 + YEAR, MAX_AGE)

    curves = track_curves(args.dataset)
    current = json.loads((args.fits / "knn-v0-nine-species-log.json").read_text())["species"]
    current_sp = json.loads((args.fits / "knn-v0-nine-species-spatial-local.json").read_text())["species"]
    comp_fit = json.loads((args.fits / "composition-af.json").read_text())["species"]

    model = SpatialBird20(args.dataset, args.geometry, args.fits / "knn-v0-nine-species-spatial-local.json")
    metrics = {}
    for label, schedule_state in (("no", None), ("cut", True)):
        if schedule_state:
            model.schedule = {int(b): float(y) for b, y in cut.items() if y <= YEAR}
            model.rebuild()
        metrics[label] = model._metrics()

    rows = []
    for bird in args.birds:
        ca = current[bird]["fit"]["coefficients"]
        cs = current_sp[bird]["coefficients"]
        na = comp_fit[bird]["aspatial"]["coefficients"]
        ns = comp_fit[bird]["spatial"]["coefficients"]
        cap_a = current[bird].get("eta_cap", 30.0)
        cap_s = current_sp[bird].get("eta_cap", 30.0)
        totals = {"ca_no": 0.0, "ca_cut": 0.0, "cs_no": 0.0, "cs_cut": 0.0,
                  "na_no": 0.0, "na_cut": 0.0, "ns_no": 0.0, "ns_cut": 0.0}
        for i in range(len(fragments)):
            ty = curves.get(int(track[i]), {})
            for label, age in (("no", age_no[i]), ("cut", age_harvest[i])):
                comp = composition(ty, int(age))
                if comp["total"] <= 0:
                    continue
                early, edge = metrics[label][0][i], metrics[label][1][i]
                a = area[i]
                totals[f"ca_{label}"] += a * np.exp(min(eta_current_aspatial(ca, age, comp["soft"], comp["hard"]), cap_a))
                totals[f"cs_{label}"] += a * np.exp(min(eta_current_spatial(cs, age, comp["soft"], comp["hard"], 1.0, edge, early), cap_s))
                totals[f"na_{label}"] += a * np.exp(min(eta_composition(na, age, comp["soft"], comp["hard"], comp), 30.0))
                totals[f"ns_{label}"] += a * np.exp(min(eta_composition(ns, age, comp["soft"], comp["hard"], comp, 1.0, edge, early), 30.0))
        row = {"bird": bird}
        for key in ("ca", "cs", "na", "ns"):
            row[f"{key}_pct"] = round(100 * (totals[f"{key}_cut"] - totals[f"{key}_no"]) / totals[f"{key}_no"], 1)
        rows.append(row)
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
