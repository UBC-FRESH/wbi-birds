"""Figure: aspatial vs spatial bird constraint (TSA41 pilot).

Panel A  harvest at equal relative bird attainment, both models (seed scatter at 85%).
Panel B  same-schedule harvest impact, nine species, both models (sign flips marked).

    python scripts/plot_dual.py --campaign dual/tsa41-gockin.csv \
        --seeds dual/tsa41-gockin-seeds.csv --impact dual/tsa41-impact.csv \
        --out images/ws4-2026-11/fig_dual_aspatial_spatial
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLORS = {"aspatial": "#b5651d", "spatial": "#1f6f8b"}
LABELS = {"aspatial": "aspatial anticipation", "spatial": "spatial anticipation"}


def rows(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def panel_a(ax, campaign: Path, seeds: Path | None, baseline: dict[str, float]) -> None:
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows(campaign):
        attainment = float(row["bird_p20"]) / baseline[row["mode"]]
        grouped[row["mode"]].append((attainment, float(row["harvest_realized_m3_yr"])))
    for mode, points in grouped.items():
        points.sort()
        ax.plot([p[0] for p in points], [p[1] for p in points], "o-",
                color=COLORS[mode], label=LABELS[mode], lw=2, ms=7)
    if seeds is not None:
        for srow in rows(seeds):
            attainment = float(srow["bird_p20"]) / baseline[srow["mode"]]
            ax.plot(attainment, float(srow["harvest_realized_m3_yr"]), "o", ms=7,
                    mfc="white", mec=COLORS[srow["mode"]], mew=1.6, zorder=5)
    ax.set_xlabel("relative bird attainment (share of each model's no-harvest GCKI)")
    ax.set_ylabel("even-flow harvest (M m$^3$ yr$^{-1}$)")
    ax.set_title("A. Harvest at equal relative attainment")
    ax.set_xticks([0.85, 0.90, 0.95])
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, loc="upper right")


def panel_b(ax, impact: Path) -> None:
    data = rows(impact)
    species = [r["species"].upper() for r in data]
    y = range(len(species))
    height = 0.38
    ax.barh([i + height / 2 for i in y], [float(r["aspatial_pct"]) for r in data],
            height=height, color=COLORS["aspatial"], label=LABELS["aspatial"])
    ax.barh([i - height / 2 for i in y], [float(r["spatial_pct"]) for r in data],
            height=height, color=COLORS["spatial"], label=LABELS["spatial"])
    for i, r in enumerate(data):
        if r["sign_flip"].lower() == "true":
            ax.text(0.98, i, "sign flip", transform=ax.get_yaxis_transform(),
                    ha="right", va="center", fontsize=8, color="crimson")
    ax.set_yticks(list(y))
    ax.set_yticklabels(species)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("period-20 abundance change under the same schedule (%)")
    ax.set_title("B. Same schedule, same landscape")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(frameon=False, loc="lower right")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--seeds", type=Path, default=None)
    parser.add_argument("--impact", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--harvest", default="1.021", help="prime schedule rate for panel B")
    parser.add_argument("--baseline-aspatial", type=float, default=1643203.0)
    parser.add_argument("--baseline-spatial", type=float, default=2035129.0)
    args = parser.parse_args()

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1, 1.15]})
    panel_a(left, args.campaign, args.seeds,
            {"aspatial": args.baseline_aspatial, "spatial": args.baseline_spatial})
    panel_b(right, args.impact)
    right.set_title(f"B. Same schedule ({args.harvest} M m$^3$ yr$^{{-1}}$)")
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out.with_suffix(".png"), dpi=200)
    fig.savefig(args.out.with_suffix(".pdf"))
    print(f"wrote {args.out}.png and .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
