"""Analyze the full TSA x species/guild curve grid and build portal data."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/srv/shared-data/gep/wbi-birds")
C = ROOT / "campaigns/ws4-five-tsa-2026-11"
D = C / "dual-full"
SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
GUILDS = ("mature_conifer", "mixedwood", "early_seral", "cavity")
INDICATORS = (*SPECIES, *GUILDS)
LABEL = {"rebnut": "RBNU", "borchi2": "BOCH", "gockin": "GCKI", "brncre": "BRCR",
         "yerwar": "YERW", "swathr": "SWTH", "whtspa": "WTSP", "tenwar": "TEWA",
         "yebsap": "YBSA", "mature_conifer": "Mature conifer", "mixedwood": "Mixedwood",
         "early_seral": "Early seral", "cavity": "Cavity"}


def curve_at(df: pd.DataFrame, base: float, target: float = 0.90) -> tuple[float, float]:
    d = df.copy()
    d["target"] = d.epsilon_p20 / base
    d["rel"] = d.bird_p20 / base
    d = d[np.isfinite(d.target) & np.isfinite(d.harvest_realized_m3_yr)]
    d = d.sort_values("target")
    g = d.groupby("target", as_index=False).agg(harvest_realized_m3_yr=("harvest_realized_m3_yr", "mean"),
                                                rel=("rel", "mean"))
    if len(g) < 2 or target < g.target.min() or target > g.target.max():
        return float("nan"), float("nan")
    return (float(np.interp(target, g.target, g.harvest_realized_m3_yr)),
            float(np.interp(target, g.target, g.rel)))


def main() -> int:
    rows = []
    curves = []
    for tsa in ("41", "40", "24", "08", "16"):
        base = json.loads((D / f"baselines-tsa{tsa}.json").read_text())
        for ind in INDICATORS:
            entry = {"tsa": f"tsa{tsa}", "indicator": ind, "label": LABEL[ind],
                     "kind": "guild" if ind in GUILDS else "species", "modes": {}}
            for mode in ("aspatial", "spatial"):
                p = D / f"tsa{tsa}-{ind}-{mode}.csv"
                if not p.exists():
                    continue
                df = pd.read_csv(p)
                if df.empty:
                    continue
                b = base[mode][ind]
                entry["modes"][mode] = [
                    {"harvest": round(float(r.harvest_realized_m3_yr), 4),
                     "relative": round(float(r.bird_p20 / b), 4),
                     "target": round(float(r.epsilon_p20 / b), 4)}
                    for r in df.itertuples()
                ]
            if len(entry["modes"]) == 2:
                curves.append(entry)
                ha, ra = curve_at(pd.read_csv(D / f"tsa{tsa}-{ind}-aspatial.csv"), base["aspatial"][ind])
                hs, rs = curve_at(pd.read_csv(D / f"tsa{tsa}-{ind}-spatial.csv"), base["spatial"][ind])
                delta = 100.0 * (ha - hs) / hs if np.isfinite(ha) and np.isfinite(hs) and hs else float("nan")
                feasible = bool(np.isfinite(ra) and np.isfinite(rs) and ra >= 0.898 and rs >= 0.898)
                rows.append(dict(tsa=f"tsa{tsa}", indicator=ind, kind=entry["kind"],
                                 aspatial_h90=ha, spatial_h90=hs, delta_pct=delta,
                                 aspatial_real90=ra, spatial_real90=rs, feasible=feasible))

    summary = pd.DataFrame(rows)
    summary.to_csv(D / "full-grid-summary.csv", index=False)
    (D / "curves.json").write_text(json.dumps(curves, indent=1))
    ok = summary[summary.feasible & summary.delta_pct.notna()]
    print(f"curves {len(curves)}; feasible {len(ok)}")
    if len(ok):
        print("median |delta|", round(float(ok.delta_pct.abs().median()), 2),
              "worst", round(float(ok.delta_pct.abs().max()), 2),
              "negative", int((ok.delta_pct < 0).sum()), "positive", int((ok.delta_pct > 0).sum()))
        print(ok.sort_values("delta_pct").head(8).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
