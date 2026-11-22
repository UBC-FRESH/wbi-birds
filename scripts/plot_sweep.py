"""Review figures for the five-TSA epsilon sweep.

Reads the aggregated points CSV and the per-TSA no-harvest endpoints, and writes:

  f1_frontier_by_species   harvest vs retention, one line per TSA
  f2_opportunity_cost      harvest lost per +0.10 retention, per species
  f3_feasibility           share of epsilon points where the bird floor was met
  f4_tsa_panels            normalized bird abundance vs harvest, one panel per TSA
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

POINTS = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/sweeps/points-production.csv")
ENDPOINTS = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/sweeps/endpoints2")
OUT = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/sweeps/figures")
OUT.mkdir(parents=True, exist_ok=True)

GUILD = {
    "rebnut": "mature conifer",
    "borchi2": "mature conifer",
    "gockin": "mature conifer",
    "brncre": "mature conifer",
    "yerwar": "mixedwood",
    "swathr": "mixedwood",
    "whtspa": "early seral",
    "tenwar": "early seral",
    "yebsap": "cavity",
}
GUILD_COLOR = {
    "mature conifer": "#1f4e79",
    "mixedwood": "#2e8b57",
    "early seral": "#c46a00",
    "cavity": "#8b3a62",
}
SPECIES = ["rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap"]
TSAS = ["41", "08", "16", "24", "40"]
TSA_COLOR = dict(zip(TSAS, ["#1b1b1b", "#1f77b4", "#2ca02c", "#d62728", "#9467bd"]))
TSA_AREA = {"41": 1.95, "08": 4.34, "16": 2.81, "24": 5.90, "40": 2.50}

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "savefig.dpi": 200,
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "legend.frameon": False,
    }
)


def load() -> pd.DataFrame:
    d = pd.read_csv(POINTS)
    d["tsa"] = d["dataset"].str.extract(r"tsa(\d+)")[0]
    none = {}
    for tsa in TSAS:
        payload = json.loads((ENDPOINTS / f"tsa{tsa}-none.json").read_text())
        for bird, values in payload["birds"].items():
            none[(tsa, bird)] = values["p20"]
    d["none_p20"] = [none[(t, b)] for t, b in zip(d.tsa, d.bird)]
    d["retention"] = 100.0 * d.epsilon / d.none_p20
    d["bird_norm"] = d.bird_p20 / d.none_p20
    return d


def fig1(d: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 3, figsize=(13.5, 10.5), sharex=True, sharey=True)
    for ax, bird in zip(axes.flat, SPECIES):
        for tsa in TSAS:
            g = d[(d.bird == bird) & (d.tsa == tsa)].sort_values("retention")
            if g.empty:
                continue
            ax.plot(
                g.retention,
                g.harvest_m3_yr,
                color=TSA_COLOR[tsa],
                lw=1.6,
                marker="o",
                ms=3.5,
                label=f"TSA {tsa}",
            )
            miss = g[~g.bird_target_met]
            ax.scatter(
                miss.retention,
                miss.harvest_m3_yr,
                c=TSA_COLOR[tsa],
                marker="x",
                s=26,
                lw=1.2,
                zorder=5,
            )
        ax.set_title(f"{bird}  ({GUILD[bird]})", color=GUILD_COLOR[GUILD[bird]])
    for ax in axes[-1]:
        ax.set_xlabel("bird retention target (% of no-harvest p20)")
    for ax in axes[:, 0]:
        ax.set_ylabel("realized even-flow harvest (M m³/yr)")
    axes[0, 0].legend(loc="lower left", fontsize=8)
    fig.suptitle(
        "Harvest frontier by species — filled markers meet the bird floor, × miss it",
        fontsize=13,
        y=0.995,
    )
    fig.tight_layout()
    fig.savefig(OUT / "f1_frontier_by_species.png", bbox_inches="tight")
    fig.savefig(OUT / "f1_frontier_by_species.pdf", bbox_inches="tight")
    plt.close(fig)


def fig2(d: pd.DataFrame) -> None:
    rows = []
    for (tsa, bird), g in d.groupby(["tsa", "bird"]):
        if len(g) < 4:
            continue
        slope = np.polyfit(g.retention, g.harvest_m3_yr, 1)[0] * 10.0
        rows.append({"tsa": tsa, "bird": bird, "slope": slope})
    s = pd.DataFrame(rows)
    order = s.groupby("bird")["slope"].median().sort_values().index.tolist()
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    med = s.groupby("bird")["slope"].median().loc[order]
    ax.barh(
        range(len(order)),
        med.values,
        color=[GUILD_COLOR[GUILD[b]] for b in order],
        alpha=0.85,
        height=0.6,
    )
    for _, row in s.iterrows():
        y = order.index(row.bird)
        ax.scatter(row.slope, y, color="white", edgecolor="black", s=16, zorder=4, lw=0.6)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("harvest change per +0.10 bird retention (M m³/yr)")
    ax.set_title("Opportunity cost of bird retention (bars = median, dots = TSAs)")
    fig.tight_layout()
    fig.savefig(OUT / "f2_opportunity_cost.png", bbox_inches="tight")
    fig.savefig(OUT / "f2_opportunity_cost.pdf", bbox_inches="tight")
    plt.close(fig)


def fig3(d: pd.DataFrame) -> None:
    grid = (
        d.groupby(["bird", "tsa"])["bird_target_met"]
        .mean()
        .unstack("tsa")
        .reindex(index=SPECIES, columns=TSAS)
        * 100.0
    )
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    im = ax.imshow(grid.values, cmap="viridis", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(TSAS)))
    ax.set_xticklabels([f"TSA {t}" for t in TSAS])
    ax.set_yticks(range(len(SPECIES)))
    ax.set_yticklabels(SPECIES)
    for i in range(len(SPECIES)):
        for j in range(len(TSAS)):
            value = grid.values[i, j]
            ax.text(
                j,
                i,
                f"{value:.0f}",
                ha="center",
                va="center",
                color="white" if value < 60 else "black",
                fontsize=9,
            )
    ax.set_title("Epsilon points meeting the bird floor (%)")
    fig.colorbar(im, ax=ax, label="% of retention levels met")
    fig.tight_layout()
    fig.savefig(OUT / "f3_feasibility.png", bbox_inches="tight")
    fig.savefig(OUT / "f3_feasibility.pdf", bbox_inches="tight")
    plt.close(fig)


def fig4(d: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(14, 8.2), sharey=True)
    for ax, tsa in zip(axes.flat, TSAS):
        for bird in SPECIES:
            g = d[(d.bird == bird) & (d.tsa == tsa)].sort_values("harvest_m3_yr")
            if g.empty:
                continue
            ax.plot(
                g.harvest_m3_yr,
                g.bird_norm,
                color=GUILD_COLOR[GUILD[bird]],
                lw=1.5,
                alpha=0.9,
            )
            ax.scatter(g.harvest_m3_yr, g.bird_norm, s=8, color=GUILD_COLOR[GUILD[bird]])
        ax.axhline(1.0, color="black", lw=0.7, ls=":")
        ax.set_yscale("log")
        ax.set_ylim(0.2, 600)
        ax.set_title(f"TSA {tsa}  ({TSA_AREA[tsa]}M ha)")
        ax.set_xlabel("harvest (M m³/yr)")
    axes[1, 2].axis("off")
    handles = [
        plt.Line2D([], [], color=GUILD_COLOR[g], lw=2, label=g) for g in GUILD_COLOR
    ]
    axes[1, 2].legend(handles=handles, loc="center left", title="guild", fontsize=10)
    for ax in axes[:, 0]:
        ax.set_ylabel("bird p20 relative to no harvest (log)")
    fig.suptitle("Guild response to harvest: mature conifer falls, early seral rises", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "f4_tsa_panels.png", bbox_inches="tight")
    fig.savefig(OUT / "f4_tsa_panels.pdf", bbox_inches="tight")
    plt.close(fig)


def fig5(d: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0))
    for ax, tsa in zip(axes, ["41", "24"]):
        for bird in SPECIES:
            g = d[(d.bird == bird) & (d.tsa == tsa)].sort_values("epsilon")
            if g.empty:
                continue
            ax.plot(g.epsilon / 1e6, g.bird_p20 / 1e6, marker="o", ms=3.5, lw=1.2,
                    color=GUILD_COLOR[GUILD[bird]], label=bird)
        lim = max(ax.get_xlim()[1], ax.get_ylim()[1])
        ax.plot([0, lim], [0, lim], ls=":", color="black", lw=0.8)
        ax.set_xlabel("epsilon target (M birds, p20)")
        ax.set_ylabel("achieved bird p20 (M)")
        ax.set_title(f"TSA {tsa}: achieved vs requested" + (" (ladder above reach)" if tsa == "24" else ""))
    axes[0].legend(fontsize=7, ncol=2, loc="upper left")
    fig.suptitle("Diagnostic: points below the 1:1 line are infeasible epsilons", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "f5_feasibility_diagnostic.png", bbox_inches="tight")
    fig.savefig(OUT / "f5_feasibility_diagnostic.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    d = load()
    fig1(d)
    fig2(d)
    fig3(d)
    fig4(d)
    fig5(d)
    print(f"{len(d)} points; figures in {OUT}")
    for path in sorted(OUT.glob("*.png")):
        print(" ", path.name, path.stat().st_size // 1024, "KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
