"""Fit composition-aware anticipation functions for the suite species.

Form (aspatial):  log(count) ~ log1p(soft) + log1p(hard) + age + composition
                                 + age x (pine, aspen, cedar)
     (spatial):   + pct_forest_1km + edge_1km + pct_early_500m

Composition groups are fractions derived from the 20 VRI species percentages.
The response is the checklist count with an effort offset, as in the probe.

    python scripts/fit_composition_af.py --birds gockin borchi2 yerwar
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import statsmodels.api as sm
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_composition_probe import build  # noqa: E402

COMPOSITION = ("pine", "spruce", "fir", "douglas", "cedar", "aspen", "birch")
SPATIAL = ("pct_forest_1km", "edge_1km", "pct_early_500m")


def fit_one(frame, bird: str, spatial: bool) -> dict:
    terms = ["log_soft", "log_hard", "age", "log_age", *COMPOSITION,
             "log_age:pine", "log_age:aspen", "log_age:cedar"]
    if spatial:
        terms += list(SPATIAL)
    formula = f"{bird} ~ " + " + ".join(terms)
    offset = np.log(frame.duration) + np.log1p(frame.distance) + np.log(frame.observers.clip(lower=1))
    model = smf.glm(formula, frame, family=sm.families.Poisson(), offset=offset).fit(maxiter=80)
    coefficients = {name: float(value) for name, value in model.params.items() if name != "Intercept"}
    coefficients["intercept"] = float(model.params["Intercept"])
    return {
        "coefficients": coefficients,
        "aic": float(model.aic),
        "dispersion": float(model.scale),
        "n": int(model.nobs),
        "form": "log1p(soft/hard) + age + composition + log1p(age) x (pine, aspen, cedar)"
                + (" + neighbourhood" if spatial else ""),
        "covariate_form": "log1p",
        "spatial_form": "local" if spatial else "aspatial",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--birds", nargs="+", default=["gockin", "borchi2", "yerwar"])
    parser.add_argument("--out", type=Path,
                        default=Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/bird-fits/composition-af.json"))
    args = parser.parse_args()

    frame = build()
    frame = frame.dropna(subset=[*args.birds, "soft_vol", "hard_vol", "age"])
    frame["log_age"] = np.log1p(frame["age"])
    print(f"fit rows: {len(frame):,}", flush=True)
    out = {"definition": "composition_aware", "link": "log (Poisson)", "species": {}}
    for bird in args.birds:
        entry = {"aspatial": fit_one(frame, bird, spatial=False),
                 "spatial": fit_one(frame, bird, spatial=True)}
        out["species"][bird] = entry
        print(f"{bird}: aspatial AIC {entry['aspatial']['aic']:,.0f}  "
              f"spatial AIC {entry['spatial']['aic']:,.0f}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
