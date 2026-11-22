"""Frontier metrics and opportunity-cost curves (F5 inputs).

For each TSA x species, from the 11 epsilon points:
  - harvest at the nadir (f=0) and at no-harvest (f=1)
  - harvest at 20/50/80% of the species' attainable range
  - cost of the middle 60% (harvest lost from f=0.2 to f=0.8)
  - convexity (second difference of harvest on attainment, normalised)
  - knee: point of maximum distance from the nadir-to-max chord in normalised space

Attainment is the same reference used in the composite:
    att = bird_p20 / ref_max(tsa, species),  ref_max including none and nadir anchors
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
TSAS = ("41", "08", "16", "24", "40")


def load(points_dir: Path, none_dir: Path) -> pd.DataFrame:
    ref = {}
    for tsa in TSAS:
        for kind, name in (("none", "none"), ("nadir", "nadir.endpoints")):
            path = none_dir / f"tsa{tsa}-{name}.json"
            if not path.exists():
                continue
            for b, v in json.loads(path.read_text())["birds"].items():
                ref[(tsa, b)] = max(ref.get((tsa, b), 0.0), v["p20"])
    rows = []
    for tsa in TSAS:
        for path in sorted((points_dir / tsa).glob("*.json")):
            d = json.loads(path.read_text())
            species = d["bird"]
            key = (tsa, species)
            if key not in ref:
                continue
            ref[key] = max(ref[key], d["bird_p20"])
            rows.append(
                {
                    "tsa": tsa,
                    "species": species,
                    "epsilon": d["epsilon"],
                    "harvest": d["harvest_m3_yr"],
                    "bird_p20": d["bird_p20"],
                    "met": d["bird_target_met"],
                }
            )
    frame = pd.DataFrame(rows)
    frame["ref_max"] = [ref[(t, s)] for t, s in zip(frame.tsa, frame.species)]
    frame["att"] = frame.bird_p20 / frame.ref_max
    return frame


def curve_metrics(g: pd.DataFrame) -> dict:
    g = g.sort_values("att")
    x = g.att.to_numpy()
    y = g.harvest.to_numpy()
    span_x = x[-1] - x[0] if x[-1] > x[0] else np.nan
    span_y = y[0] - y[-1] if y[0] > y[-1] else 1e-9
    xn = (x - x[0]) / span_x if span_x and np.isfinite(span_x) else x * np.nan
    yn = (y - y[-1]) / span_y

    def at(target: float) -> float:
        return float(np.interp(target, x, y)) if np.isfinite(span_x) else np.nan

    # knee: max perpendicular distance below the chord (x_n, y_n)
    knee = np.nan
    best = -np.inf
    for i in range(1, len(xn) - 1):
        dist = (yn[i] - (1 - xn[i])) * -1  # chord y = 1 - x
        if dist > best:
            best = dist
            knee = float(x[i])

    convexity = float(np.mean(np.diff(y, 2))) if len(y) >= 3 else np.nan
    return {
        "harvest_nadir": float(y[0]),
        "harvest_max": float(y[-1]),
        "harvest_at_20": at(x[0] + 0.2 * span_x),
        "harvest_at_50": at(x[0] + 0.5 * span_x),
        "harvest_at_80": at(x[0] + 0.8 * span_x),
        "cost_mid60": float(at(x[0] + 0.2 * span_x) - at(x[0] + 0.8 * span_x)),
        "cost_per_10pct": float((y[0] - y[-1]) / max(span_x, 1e-9) * 0.1),
        "convexity": convexity,
        "knee_attainment": knee,
        "n": len(g),
        "met": int(g.met.sum()),
    }


TSA_COLOR = {"41": "#1b1b1b", "08": "#1f77b4", "16": "#2ca02c", "24": "#d62728", "40": "#9467bd"}


def plot(frame: pd.DataFrame, metrics: pd.DataFrame, out: Path) -> None:
    plt.rcParams.update({"savefig.dpi": 200, "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
                         "legend.frameon": False})
    fig, axes = plt.subplots(3, 3, figsize=(13.5, 10), sharex=True, sharey=True)
    for ax, species in zip(axes.flat, SPECIES):
        cost = metrics[metrics.species == species].cost_mid60.median()
        for tsa in TSAS:
            g = frame[(frame.tsa == tsa) & (frame.species == species)].sort_values("att")
            if len(g) < 3:
                continue
            ax.plot(g.att, g.harvest, color=TSA_COLOR[tsa], lw=1.5, marker="o", ms=3.2, label=f"TSA {tsa}")
            kne = metrics[(metrics.tsa == tsa) & (metrics.species == species)].knee_attainment
            if len(kne) and np.isfinite(kne.iloc[0]):
                y = np.interp(kne.iloc[0], g.att, g.harvest)
                ax.scatter([kne.iloc[0]], [y], s=42, facecolor="white",
                           edgecolor=TSA_COLOR[tsa], zorder=5, lw=1.4)
        ax.set_title(f"{species}   median cost {cost:.2f} M m³/yr")
    for ax in axes[-1]:
        ax.set_xlabel("attainment (share of campaign best)")
    for ax in axes[:, 0]:
        ax.set_ylabel("realized harvest (M m³/yr)")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Opportunity-cost curves: harvest vs bird attainment (open circles = knees)", fontsize=13)
    fig.tight_layout()
    fig.savefig(out / "f5_opportunity_curves.png", bbox_inches="tight")
    fig.savefig(out / "f5_opportunity_curves.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--none", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    frame = load(args.points, args.none)
    rows = []
    for (tsa, species), g in frame.groupby(["tsa", "species"]):
        if len(g) < 4:
            continue
        rows.append({"tsa": tsa, "species": species, **curve_metrics(g)})
    metrics = pd.DataFrame(rows).sort_values(["tsa", "species"])
    args.out.mkdir(parents=True, exist_ok=True)
    plot(frame, metrics, args.out)
    metrics.to_csv(args.out / "frontier_metrics.csv", index=False)

    print("cost of the middle 60% of attainable range (M m3/yr), by species x TSA:")
    pivot = metrics.pivot(index="species", columns="tsa", values="cost_mid60").reindex(SPECIES)
    print(pivot.round(2).to_string())
    print("\nmedian by species:")
    print(metrics.groupby("species").agg(
        cost_mid60=("cost_mid60", "median"),
        cost_per_10pct=("cost_per_10pct", "median"),
        knee=("knee_attainment", "median"),
        met=("met", "sum"),
    ).round(3).reindex(SPECIES).to_string())
    print(f"\nwrote {args.out / 'frontier_metrics.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
