"""Compact-genome GA benchmark for the wood-supply objective.

Genome: one harvest age per managed track (40-300, 10-year steps). Unmanaged tracks
are never harvested. A deterministic builder assigns each block its first harvest when
it reaches the track's target age within the horizon.

Evaluation is vectorised (no ws4 state): per-period harvest from track/age volume
matrices, aspatial bird totals from the log AF, objective = level pull + even flow
(+ optional bird floor). This is a search-strategy benchmark against the SA, not the
production campaign.

    python scripts/ga_compact.py --dataset <dir> --fits <json> [--pop 40] [--gens 100]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
HARD = {"AT", "AC", "ACT", "EP"}
YEARS, PERIOD = 200, 10
PERIODS = YEARS // PERIOD
MAX_AGE = 300
AGES = np.arange(40, 301, 10)


def matrices(dataset: Path):
    feats = pd.read_parquet(dataset / "features.parquet")
    curves = pd.read_parquet(dataset / "curves.parquet")
    mt = int(feats.track_id.max())
    total = np.zeros((mt + 1, MAX_AGE + 1), dtype=np.float32)
    sw = np.zeros_like(total)
    hw = np.zeros_like(total)
    grid = np.arange(MAX_AGE + 1, dtype=float)
    for track, rows in feats.groupby("track_id"):
        for label, cid in zip(rows.label, rows.curve_id):
            parts = str(label).split(".")
            if len(parts) != 4 or parts[0] != "feature" or parts[1] != "Yield":
                continue
            c = curves[curves.curve_id == int(cid)].sort_values("x")
            values = np.interp(grid, c.x.to_numpy(float), c.y.to_numpy(float),
                               left=0.0, right=float(c.y.iloc[-1]))
            if parts[3] == "Total":
                total[int(track), :] = values
            elif parts[3] in HARD:
                hw[int(track), :] += values
            else:
                sw[int(track), :] += values
    return total, sw, hw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--fits", type=Path, required=True)
    ap.add_argument("--pop", type=int, default=40)
    ap.add_argument("--gens", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--level", type=float, default=40e6)
    ap.add_argument("--band", type=float, default=10.0)
    args = ap.parse_args()

    frag = pd.read_parquet(args.dataset / "fragments.parquet")
    treat = pd.read_parquet(args.dataset / "treatments.parquet")
    managed = np.array(sorted(int(t) for t in treat.track_id.unique()))
    n = len(frag)
    initial = frag["age"].to_numpy(float)
    area = frag["area_ha"].to_numpy(float)
    track = frag["track_id"].to_numpy(int)
    TOTAL, SW, HW = matrices(args.dataset)
    fits = json.loads(args.fits.read_text())["species"]

    managed_mask = np.isin(track, managed)
    idx_managed = np.flatnonzero(managed_mask)
    track_pos = {int(t): i for i, t in enumerate(managed)}

    def evaluate(genome: np.ndarray) -> tuple[float, float, np.ndarray]:
        target = dict(zip(managed.tolist(), genome.tolist()))
        harvest = np.zeros(PERIODS)
        bird = np.zeros((PERIODS, len(SPECIES)))
        # vectorised harvest year per block
        years = np.full(n, -1)
        for i in idx_managed:
            t = int(track[i])
            ta = target[t]
            y = ta - initial[i]
            if 0 <= y < YEARS:
                years[i] = y
        for period in range(PERIODS):
            lo, hi = period * PERIOD, (period + 1) * PERIOD
            sel = (years >= lo) & (years < hi)
            if sel.any():
                vol = TOTAL[track[sel], np.clip((initial[sel] + years[sel]).astype(int), 0, MAX_AGE)]
                harvest[period] = float(np.sum(area[sel] * vol))
            age = np.clip(initial + (period + 1) * PERIOD, 0, MAX_AGE)
            age = np.where(years >= 0, (period + 1) * PERIOD - years, age)
            age_clip = np.clip(age, 0, MAX_AGE).astype(int)
            for k, sp in enumerate(SPECIES):
                c = fits[sp]["fit"]["coefficients"]
                eta = (c["intercept"] + c["softwood"] * np.log1p(SW[track, age_clip])
                       + c["hardwood"] * np.log1p(HW[track, age_clip]) + c["age"] * age)
                bird[period, k] = float(np.sum(area * np.exp(np.clip(eta, -30, fits[sp]["eta_cap"]))))
        level_pen = float(np.sum(np.maximum(0.0, args.level - harvest)))
        ref = harvest[-1]
        flow = 100.0 * (harvest - ref) / np.maximum(ref, 1.0)
        flow_pen = float(np.sum(np.maximum(0.0, np.abs(flow) - args.band)) ** 2) * 10000.0
        return level_pen + flow_pen, float(harvest.mean() / 1e6), bird[-1]

    rng = np.random.default_rng(args.seed)
    pop = rng.choice(AGES, size=(args.pop, len(managed)))
    fit = np.array([evaluate(g)[0] for g in pop])
    print(f"pop {args.pop} genes {len(managed)}  gen0 best {fit.min():.3g}")
    t0 = time.time()
    for gen in range(args.gens):
        order = np.argsort(fit)
        elite = pop[order[:2]]
        new = list(elite)
        while len(new) < args.pop:
            a, b = rng.integers(0, args.pop, 2)
            parent = pop[a] if fit[a] < fit[b] else pop[b]
            child = parent.copy()
            mask = rng.random(len(managed)) < 0.5
            other = pop[rng.integers(0, args.pop)]
            child[mask] = other[mask]
            mut = rng.random(len(managed)) < 0.15
            child[mut] = rng.choice(AGES, int(mut.sum()))
            new.append(child)
        pop = np.array(new)
        fit = np.array([evaluate(g)[0] for g in pop])
        if gen % 10 == 0:
            print(f"gen {gen} best {fit.min():.3g}  {time.time()-t0:.0f}s", flush=True)
    best = pop[int(np.argmin(fit))]
    obj, harvest, bird = evaluate(best)
    print(f"final objective {obj:.3g}  mean harvest {harvest:.3f} M/yr")
    print("harvest profile:", np.round(np.arange(len(best)), 0).astype(int).tolist()[:0] or "n/a")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
