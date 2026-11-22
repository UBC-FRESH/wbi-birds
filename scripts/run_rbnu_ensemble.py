#!/usr/bin/env python
"""Fit and stage the RBNU ensemble from the validated 65,373-row kNN sample.

The nine-species zero-fill exists, but the covariate rasters for its 820,927
checklist locations are not in the private store. The RBNU sample is the
validated technical path and uses the accepted ``volume_allocated`` contract.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from wbi_birds.bird import reachable_state_space
from wbi_birds.covariates import build_covariate_rows
from wbi_birds.ensemble import DEFAULT_FAMILIES, fit_ensemble
from wbi_birds.fit import stage_ensemble_response
from wbi_birds.model import build_model

STORE = Path("/srv/shared-data/gep/wbi-birds/wbi-ebird-data")
INSTANCE = Path("/srv/shared-data/gep/wbi-birds/campaigns/rbnu-contract-full/TSA24/instance")
SAMPLE = STORE / "derived" / "rbnu-legacy" / "rbnu_legacy_samples.npz"

SOFTWOOD = (
    "Pice_Eng", "Pice_Gla", "Pice_Mar", "Pinu_Con", "Pseu_Men", "Abie_Las",
    "Pinu_Mon", "Tsug_Mer", "Lari_Lya", "Pinu_Alb", "Pice_Spp", "Abie_Ama",
    "Lari_Lar", "Tsug_Het", "Abie_Bal", "Thuj_Pli",
)
HARDWOOD = ("Popu_Tre", "Popu_Spp", "Sali_Spp", "Popu_Tri", "Betu_Pap")


def main() -> int:
    sample = np.load(SAMPLE)
    samples = {name: sample[name] for name in (*SOFTWOOD, *HARDWOOD, "mvol", "age")}
    rows = build_covariate_rows(
        samples,
        softwood_species=SOFTWOOD,
        hardwood_species=HARDWOOD,
        merchantable_volume="mvol",
        knn_age="age",
        observation_year=sample["year"],
        definition="volume_allocated",
        response=sample["count"],
    )
    raw = np.array([[r["softwood"], r["hardwood"], r["age"]] for r in rows], dtype=float)
    counts = np.array([r["observation_count"] for r in rows], dtype=float)
    print(f"rows={len(rows)} raw={raw.shape} counts={counts.shape}")

    ensemble = fit_ensemble(raw, counts, DEFAULT_FAMILIES, folds=5, seed=0)
    print(json.dumps(ensemble.report(), indent=2, sort_keys=True, default=float))

    model, stats = build_model(INSTANCE)
    states = reachable_state_space(model, acodes=("null", "cc"))
    path = stage_ensemble_response(model, "rebnut", ensemble, INSTANCE, states=states)
    print(f"staged={path} states={len(states)} dtypes={stats.dtype_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
