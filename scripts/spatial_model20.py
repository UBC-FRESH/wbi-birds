"""Period-20 spatial bird model (the constraint period).

The epsilon constraints act on bird abundance at period 20, so only that state is
needed: ages at year 199, one 250 m class grid, local metric updates.

    model = SpatialBird20(dataset, geometry, fits)
    model.apply({block: year_or_None, ...})   # returns per-species delta totals
    model.totals()                            # {species: total}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import wkb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_evaluator import RasterState, classify  # noqa: E402

SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
GUILDS = {
    "mature_conifer": ("rebnut", "borchi2", "gockin", "brncre"),
    "mixedwood": ("yerwar", "swathr"),
    "early_seral": ("whtspa", "tenwar"),
    "cavity": ("yebsap",),
}
HARD = {"AT", "AC", "ACT", "EP"}
YEAR = 199  # period-20 end
MAX_AGE = 300


def _volumes(dataset: Path):
    feats = pd.read_parquet(dataset / "features.parquet")
    curves = pd.read_parquet(dataset / "curves.parquet")
    mt = int(feats.track_id.max())
    sw = np.zeros((mt + 1, MAX_AGE + 1), np.float32)
    hw = np.zeros((mt + 1, MAX_AGE + 1), np.float32)
    grid = np.arange(MAX_AGE + 1, dtype=float)
    for track, rows in feats.groupby("track_id"):
        for label, cid in zip(rows.label, rows.curve_id):
            parts = str(label).split(".")
            if len(parts) == 4 and parts[0] == "feature" and parts[1] == "Yield" and parts[3] != "Total":
                c = curves[curves.curve_id == int(cid)].sort_values("x")
                vals = np.interp(grid, c.x.to_numpy(float), c.y.to_numpy(float),
                                 left=0.0, right=float(c.y.iloc[-1]))
                (hw if parts[3] in HARD else sw)[int(track), :] += vals
    return sw, hw


class SpatialBird20:
    def __init__(self, dataset: Path, geometry: Path, fits: Path, species: str | None = None,
                 guild: str | None = None):
        frag = pd.read_parquet(dataset / "fragments.parquet")
        ids = frag["block_id"].to_numpy(int)
        if not np.array_equal(ids, np.arange(len(ids))):
            raise ValueError("fragment rows are not block-id ordered; cannot index by block id")
        self.n = len(frag)
        self.guild_key = guild
        if guild is not None:
            self.species = GUILDS[guild]
        else:
            self.species = tuple(SPECIES) if species is None else (species,)
        self.initial = frag["age"].to_numpy(float)
        self.area = frag["area_ha"].to_numpy(float)
        self.track = frag["track_id"].to_numpy(int)
        self.sw, self.hw = _volumes(dataset)
        self.fits = json.loads(fits.read_text())["species"]
        self.geoms = [wkb.loads(x) for x in pd.read_feather(geometry).geometry]
        geoms = self.geoms
        self.schedule: dict[int, float] = {}
        self.age20 = np.minimum(self.initial + YEAR, MAX_AGE)
        ages = self.age20
        self.raster = RasterState.build(geoms, self.n, ages)
        self.cells = self.raster.cells
        self.values = self._values_all(self._metrics())
        self._tot = self._sum_values()

    def rebuild(self) -> None:
        """Full oracle: rebuild raster and values from the current schedule."""
        self.age20 = self.ages()
        self.raster = RasterState.build(self.geoms, self.n, self.age20)
        self.values = self._values_all(self._metrics())
        self._tot = self._sum_values()

    def ages(self) -> np.ndarray:
        """Clamped period-20 ages rebuilt from the full schedule (rebuild path)."""
        age = np.minimum(self.initial + YEAR, MAX_AGE)
        for block, year in self.schedule.items():
            age[block] = min(max(YEAR - year, 0.0), MAX_AGE)
        return age

    def _metrics(self):
        cell_block = self.raster.block_grid.ravel()
        valid = cell_block >= 0
        counts = np.bincount(cell_block[valid], minlength=self.n)
        out = []
        for grid in (self.raster.early.ravel(), self.raster.edge.ravel()):
            total = np.bincount(cell_block[valid], weights=grid[valid], minlength=self.n)
            out.append((total / np.maximum(counts, 1)).astype(np.float32))
        return out

    def _values_all(self, metrics) -> dict[str, np.ndarray]:
        early, edge = metrics
        ages = np.minimum(self.ages(), MAX_AGE)
        clip = ages.astype(int)
        sw = self.sw[self.track, clip]
        hw = self.hw[self.track, clip]
        values = {}
        for sp in self.species:
            c = self.fits[sp]["coefficients"]
            eta = (c["intercept"] + c["log1p_softwood"] * np.log1p(sw) + c["log1p_hardwood"] * np.log1p(hw)
                   + c["age"] * ages + c["pct_forest_1km"] + c["edge_1km"] * edge + c["pct_early_500m"] * early)
            values[sp] = (self.area * np.exp(np.clip(eta, -30, self.fits[sp]["eta_cap"]))).astype(np.float32)
        return values

    def _sum_values(self) -> dict[str, float]:
        totals = {sp: float(v.sum()) for sp, v in self.values.items()}
        if self.guild_key is not None:
            totals[self.guild_key] = float(sum(totals[sp] for sp in self.species))
        return totals

    def totals(self) -> dict[str, float]:
        return dict(self._tot)

    def current(self, block: int) -> float | None:
        """Return the harvest year currently applied to ``block`` at period 20."""
        return self.schedule.get(int(block))

    def rescore(self, schedule: dict[int, float]) -> dict[str, float]:
        """Evaluate a complete schedule without re-rasterising the landscape."""
        self.schedule = {int(b): float(y) for b, y in schedule.items()}
        self.age20 = self.ages()
        self.raster.class_of_block = classify(self.age20)
        self.raster.sync_classes()
        self.raster.recompute()
        self.values = self._values_all(self._metrics())
        self._tot = self._sum_values()
        return dict(self._tot)

    def reset(self, schedule: dict[int, float]) -> None:
        """Replace the whole schedule and rebuild from scratch (end of a run)."""
        self.schedule = {int(b): float(y) for b, y in schedule.items()}
        self.rebuild()

    def _affected(self, blocks) -> set[int]:
        cell_block = self.raster.block_grid
        h, w = cell_block.shape
        out: set[int] = set()
        for b in blocks:
            idx = self.cells[b]
            if idx.size == 0:
                out.add(b)
                continue
            rows = idx // w
            cols = idx % w
            r0 = max(0, int(rows.min()) - 8); r1 = min(h, int(rows.max()) + 9)
            c0 = max(0, int(cols.min()) - 8); c1 = min(w, int(cols.max()) + 9)
            window = cell_block[r0:r1, c0:c1]
            out.update(int(x) for x in np.unique(window) if x >= 0)
        return out

    def apply(self, changes: dict[int, float | None]) -> dict[str, float]:
        """Set block harvest years (None = untreated) and return total deltas."""
        before = dict(self._tot)
        for block, year in changes.items():
            b = int(block)
            if year is None:
                self.schedule.pop(b, None)
                self.age20[b] = min(self.initial[b] + YEAR, MAX_AGE)
            else:
                self.schedule[b] = float(year)
                self.age20[b] = min(max(YEAR - float(year), 0.0), MAX_AGE)
        ages_new = self.age20
        changed = []
        for b in changes:
            code = classify(np.array([ages_new[b]]))[0]
            if code != self.raster.class_of_block[b]:
                self.raster.class_of_block[b] = code
                changed.append(int(b))
        if changed:
            affected = self._affected(changed) | {int(b) for b in changes}
            self.raster.update(changed)
        else:
            affected = {int(b) for b in changes}
        if affected:
            sub = np.sort(np.fromiter(affected, dtype=np.int64, count=len(affected)))
            sizes = np.fromiter((self.cells[int(b)].size for b in sub), dtype=np.int64,
                                count=len(sub))
            keep = np.nonzero(sizes)[0]
            early = np.zeros(len(sub), dtype=np.float32)
            edge = np.zeros(len(sub), dtype=np.float32)
            if keep.size:
                idx = np.concatenate([self.cells[int(sub[i])] for i in keep])
                owner = np.repeat(keep, sizes[keep])
                early_all = self.raster.early.ravel()
                edge_all = self.raster.edge.ravel()
                scale = np.maximum(sizes, 1)
                early = (np.bincount(owner, weights=early_all[idx], minlength=len(sub))
                         / scale).astype(np.float32)
                edge = (np.bincount(owner, weights=edge_all[idx], minlength=len(sub))
                        / scale).astype(np.float32)
            clip = ages_new[sub].astype(int)
            sw = self.sw[self.track[sub], clip]
            hw = self.hw[self.track[sub], clip]
            area = self.area[sub]
            for sp in self.species:
                c = self.fits[sp]["coefficients"]
                eta = (c["intercept"] + c["log1p_softwood"] * np.log1p(sw)
                       + c["log1p_hardwood"] * np.log1p(hw)
                       + c["age"] * ages_new[sub] + c["pct_forest_1km"]
                       + c["edge_1km"] * edge + c["pct_early_500m"] * early)
                new = (area * np.exp(np.clip(eta, -30, self.fits[sp]["eta_cap"]))).astype(np.float32)
                self._tot[sp] += float(new.sum()) - float(self.values[sp][sub].sum())
                self.values[sp][sub] = new
            if self.guild_key is not None:
                self._tot[self.guild_key] = float(sum(self._tot[sp] for sp in self.species))
        delta = {sp: self._tot[sp] - before[sp] for sp in self.species}
        if self.guild_key is not None:
            delta[self.guild_key] = self._tot[self.guild_key] - before.get(self.guild_key, 0.0)
        return delta

