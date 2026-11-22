"""Compare epsilon-constraint frontiers across even-flow bands (epsilon_p).

Inputs are one (band, points_dir, birds_dir) triple per run. For each band this
rebuilds the same composite used in plot_composite (attainment relative to the
campaign best, guild means) and reports how the frontier shifts with the band.

    python compare_bands.py \
      --band 8  results3 results3-birds \
      --band 10 results4 results4-birds \
      --band 5  results5 results5-birds \
      --band 15 results6 results6-birds \
      --none endpoints2 --out figures
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pc = load_module("plot_composite")

BAND_COLOR = {5: "#1f77b4", 8: "#2ca02c", 10: "#1b1b1b", 15: "#d62728"}
TSAS = ("41", "08", "16", "24", "40")
SPECIES_SHOW = ("borchi2", "gockin", "yerwar")


def envelope(frame: pd.DataFrame, value: str, bins: int = 10) -> pd.DataFrame:
    out = []
    edges = np.unique(np.quantile(frame.harvest, np.linspace(0, 1, bins + 1)))
    for low, high in zip(edges[:-1], edges[1:]):
        chunk = frame[(frame.harvest >= low) & (frame.harvest <= high)]
        if chunk.empty:
            continue
        best = chunk.loc[chunk[value].idxmax()]
        out.append({"harvest": float(chunk.harvest.mean()), "value": float(best[value])})
    return pd.DataFrame(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", nargs=3, action="append", required=True,
                        metavar=("BAND", "POINTS", "BIRDS"))
    parser.add_argument("--none", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cap", type=float, default=2.0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    frames = []
    for band, points, birds in args.band:
        long = pc.build(Path(points), Path(birds), args.none)
        if long.empty:
            print(f"band {band}: no joined points (birds pass incomplete?)")
            continue
        wide = pc.summarise(long, args.cap)
        wide["band"] = int(band)
        frames.append(wide)
        print(f"band {band}: {len(wide)} points")
    if not frames:
        print("nothing to compare")
        return 1
    allb = pd.concat(frames, ignore_index=True)
    allb.to_csv(args.out / "bands_points.csv", index=False)

    bands = sorted(allb.band.unique())

    # 1. composite envelope per TSA, one line per band
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharey=True)
    for ax, tsa in zip(axes.flat, TSAS):
        g = allb[allb.tsa == tsa]
        for band in bands:
            h = g[g.band == band]
            if h.empty:
                continue
            env = envelope(h, "index_att")
            if env.empty:
                continue
            ax.plot(env.harvest, env.value, color=BAND_COLOR.get(band, "grey"), lw=1.8,
                    marker="o", ms=3, label=f"±{band}%")
        ax.set_title(f"TSA {tsa}")
        ax.set_xlabel("harvest (M m³/yr)")
    for ax in axes[:, 0]:
        ax.set_ylabel("composite attainment  I")
    axes[1, 2].axis("off")
    axes[1, 2].legend(*axes[0, 0].get_legend_handles_labels(), loc="center left",
                      title="even-flow band")
    fig.suptitle("Composite frontier by even-flow band (upper envelope)", fontsize=13)
    fig.tight_layout()
    fig.savefig(args.out / "f8_band_sensitivity.png", bbox_inches="tight")
    fig.savefig(args.out / "f8_band_sensitivity.pdf", bbox_inches="tight")
    plt.close(fig)

    # 2. binding species: harvest vs attainment per band
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), sharey=True)
    for ax, species in zip(axes, SPECIES_SHOW):
        for band in bands:
            h = allb[(allb.band == band) & (allb.constrained == species)]
            if h.empty:
                continue
            env = envelope(h, "index_att")
            if env.empty:
                continue
            ax.plot(env.harvest, env.value, color=BAND_COLOR.get(band, "grey"), lw=1.6, label=f"±{band}%")
        ax.set_title(species)
        ax.set_xlabel("harvest (M m³/yr)")
    axes[0].set_ylabel("composite attainment  I")
    axes[0].legend(fontsize=8)
    fig.suptitle("Binding-species frontiers by band", fontsize=12)
    fig.tight_layout()
    fig.savefig(args.out / "f9_band_binding_species.png", bbox_inches="tight")
    fig.savefig(args.out / "f9_band_binding_species.pdf", bbox_inches="tight")
    plt.close(fig)

    # 3. summary: harvest at 0.5 and 0.8 composite attainment, per band and TSA
    rows = []
    for (band, tsa), g in allb.groupby(["band", "tsa"]):
        def max_harvest(threshold: float) -> float:
            eligible = g[g.index_att >= threshold]
            return float(eligible.harvest.max()) if not eligible.empty else float("nan")

        rows.append({
            "band": band, "tsa": tsa,
            "harvest_max_at_I50": max_harvest(0.50),
            "harvest_max_at_I80": max_harvest(0.80),
            "I_max": float(g.index_att.max()),
        })
    summary = pd.DataFrame(rows).sort_values(["tsa", "band"])
    summary.to_csv(args.out / "band_frontier_summary.csv", index=False)
    print("\nmax harvest with composite I >= 0.5 / 0.8 (M m3/yr):")
    print(summary.round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
