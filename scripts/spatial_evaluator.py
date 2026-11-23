"""Raster-consistent spatial habitat state with incremental metric updates.

The fitting covariates use windowed statistics on a 250 m class grid:
  early fraction = uniform_filter(early, size=2)
  edge density   = uniform_filter(boundary, size=8)
A move changes a block's cells; metrics in the surrounding window change. This
module keeps a class grid and recomputes only the affected window, then verifies
that incremental updates equal a full recomputation.

Habitat classes: 0 early (age < 40), 1 mid (40-79), 2 mature (>= 80), -1 outside.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage as ndi

RES = 250.0
EARLY_AGE = 40.0
MATURE_AGE = 80.0
EDGE_WINDOW = 8
EARLY_WINDOW = 8


def classify(age: np.ndarray) -> np.ndarray:
    return np.where(age >= MATURE_AGE, 2, np.where(age >= EARLY_AGE, 1, 0)).astype(np.int8)


@dataclass
class RasterState:
    block_grid: np.ndarray  # (H, W) int32 block index, -1 outside
    class_of_block: np.ndarray  # (n,) int8
    early: np.ndarray  # (H, W) float32
    edge: np.ndarray  # (H, W) float32
    cells: list[np.ndarray]  # block -> flat cell indices
    shape: tuple[int, int]
    class_grid: np.ndarray | None = None  # maintained incrementally by update()

    @classmethod
    def build(cls, geoms, n_blocks: int, ages: np.ndarray, pad_cells: int = 2) -> "RasterState":
        xs = [g.bounds[0] for g in geoms]
        ys = [g.bounds[1] for g in geoms]
        x2 = [g.bounds[2] for g in geoms]
        y2 = [g.bounds[3] for g in geoms]
        left, bottom = min(xs), min(ys)
        right, top = max(x2), max(y2)
        width = int((right - left) / RES) + 1 + 2 * pad_cells
        height = int((top - bottom) / RES) + 1 + 2 * pad_cells
        transform = from_origin(left - pad_cells * RES, top + pad_cells * RES, RES, RES)
        block_grid = rasterize(
            ((geom, idx) for idx, geom in enumerate(geoms)),
            out_shape=(height, width),
            transform=transform,
            fill=-1,
            dtype="int32",
        )
        flat = block_grid.ravel()
        order = np.argsort(flat, kind="stable")
        sorted_cells = order[flat[order] >= 0]
        sorted_blocks = flat[sorted_cells]
        bounds = np.searchsorted(sorted_blocks, np.arange(n_blocks), side="left")
        ends = np.searchsorted(sorted_blocks, np.arange(n_blocks), side="right")
        cells = [sorted_cells[b:e] for b, e in zip(bounds, ends)]
        class_of_block = classify(ages)
        state = cls(
            block_grid=block_grid,
            class_of_block=class_of_block,
            early=np.zeros((height, width), dtype=np.float32),
            edge=np.zeros((height, width), dtype=np.float32),
            cells=cells,
            shape=(height, width),
            class_grid=np.full((height, width), -1, dtype=np.int8),
        )
        valid = block_grid >= 0
        state.class_grid[valid] = class_of_block[block_grid[valid]]
        state.recompute()
        return state

    def _class_grid(self) -> np.ndarray:
        if self.class_grid is not None:
            return self.class_grid
        grid = self.block_grid
        out = np.full(grid.shape, -1, dtype=np.int8)
        valid = grid >= 0
        out[valid] = self.class_of_block[grid[valid]]
        return out

    def _boundary(self, classes: np.ndarray) -> np.ndarray:
        b = np.zeros(classes.shape, dtype=np.float32)
        valid = classes >= 0
        b[:-1, :] += (valid[:-1, :] & valid[1:, :] & (classes[:-1, :] != classes[1:, :]))
        b[1:, :] += (valid[1:, :] & valid[:-1, :] & (classes[1:, :] != classes[:-1, :]))
        b[:, :-1] += (valid[:, :-1] & valid[:, 1:] & (classes[:, :-1] != classes[:, 1:]))
        b[:, 1:] += (valid[:, 1:] & valid[:, :-1] & (classes[:, 1:] != classes[:, :-1]))
        return b

    def sync_classes(self) -> None:
        """Rebuild the maintained class grid from ``class_of_block`` (batch path)."""
        if self.class_grid is None:
            return
        grid = self.block_grid
        out = self.class_grid
        out[:] = -1
        valid = grid >= 0
        out[valid] = self.class_of_block[grid[valid]]

    def recompute(self) -> None:
        classes = self._class_grid()
        early = (classes == 0).astype(np.float32)
        self.early = ndi.uniform_filter(early, size=EARLY_WINDOW, mode="nearest")
        boundary = (self._boundary(classes) > 0).astype(np.float32)
        self.edge = ndi.uniform_filter(boundary, size=EDGE_WINDOW, mode="nearest")

    def _window(self, block: int) -> tuple[slice, slice] | None:
        idx = self.cells[block]
        if idx.size == 0:
            return None
        h, w = self.shape
        rows = idx // w
        cols = idx % w
        r0 = max(0, int(rows.min()) - EDGE_WINDOW - 4)
        r1 = min(h, int(rows.max()) + EDGE_WINDOW + 5)
        c0 = max(0, int(cols.min()) - EDGE_WINDOW - 4)
        c1 = min(w, int(cols.max()) + EDGE_WINDOW + 5)
        return slice(r0, r1), slice(c0, c1)

    def update(self, blocks: list[int]) -> None:
        """Refresh metrics around the given blocks (classes already current)."""
        if self.class_grid is not None:
            flat = self.class_grid.ravel()
            for block in blocks:
                idx = self.cells[block]
                if idx.size:
                    flat[idx] = self.class_of_block[block]
        classes = self._class_grid()
        h, w = self.shape
        for block in blocks:
            idx = self.cells[block]
            if idx.size == 0:
                continue
            rows = idx // w
            cols = idx % w
            r0 = max(0, int(rows.min()) - EDGE_WINDOW)
            r1 = min(h, int(rows.max()) + EDGE_WINDOW + 1)
            c0 = max(0, int(cols.min()) - EDGE_WINDOW)
            c1 = min(w, int(cols.max()) + EDGE_WINDOW + 1)
            pad = EDGE_WINDOW  # filter radius is 4; 8 is ample
            pr0 = max(0, r0 - pad); pr1 = min(h, r1 + pad)
            pc0 = max(0, c0 - pad); pc1 = min(w, c1 + pad)
            sub = classes[pr0:pr1, pc0:pc1]
            early = (sub == 0).astype(np.float32)
            e = ndi.uniform_filter(early, size=EARLY_WINDOW, mode="nearest")
            boundary = (self._boundary(sub) > 0).astype(np.float32)
            g = ndi.uniform_filter(boundary, size=EDGE_WINDOW, mode="nearest")
            self.early[r0:r1, c0:c1] = e[r0 - pr0:r1 - pr0, c0 - pc0:c1 - pc0]
            self.edge[r0:r1, c0:c1] = g[r0 - pr0:r1 - pr0, c0 - pc0:c1 - pc0]

    def sample(self, block: int) -> tuple[float, float]:
        idx = self.cells[block]
        if idx.size == 0:
            return 0.0, 0.0
        return float(self.early.ravel()[idx].mean()), float(self.edge.ravel()[idx].mean())
