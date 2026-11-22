"""Composite bird indicators from the nine-species sweep.

Two normalisations, reported together because they answer different questions:

  R_none = bird_s / none_s                   "retention vs the unharvested baseline"
  R_att  = bird_s / ref_max_s                "attainment of the best achievable level"

R_none is ill-conditioned for species whose habitat harvest creates: where
none_s is near zero (YBSA at TSA41: 26k vs 27M under harvest) the ratio reaches
1e3 and dominates any mean.  It is therefore reported capped at --cap (default 2)
and never as the headline.

R_att uses ref_max_s = the largest period-20 value that species reaches in the
campaign (its own points plus the no-harvest and nadir anchors), so it is bounded
in [0, 1] and reads as "share of this species' best case".

Composite:
    I = mean_s R_s                    (equal weight per species)
    I_g = mean_{s in guild} R_s       (guild means)
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SPECIES = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
GUILD = {
    "rebnut": "mature conifer", "borchi2": "mature conifer",
    "gockin": "mature conifer", "brncre": "mature conifer",
    "yerwar": "mixedwood", "swathr": "mixedwood",
    "whtspa": "early seral", "tenwar": "early seral",
    "yebsap": "cavity",
}
GUILDS = ("mature conifer", "mixedwood", "early seral", "cavity")
GUILD_COLOR = {"mature conifer": "#1f4e79", "mixedwood": "#2e8b57",
               "early seral": "#c46a00", "cavity": "#8b3a62"}
TSA_COLOR = {"41": "#1b1b1b", "08": "#1f77b4", "16": "#2ca02c", "24": "#d62728", "40": "#9467bd"}
TAG = re.compile(r"tsa(\d+)-([a-z0-9]+)-e([0-9.]+)")

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 200, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "legend.frameon": False,
})


def build(points_dir: Path, birds_dir: Path, none_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    anchors = {}
    for tsa in ("41", "08", "16", "24", "40"):
        none_path = none_dir / f"tsa{tsa}-none.json"
        nadir_path = none_dir / f"tsa{tsa}-nadir.endpoints.json"
        if none_path.exists():
            anchors.setdefault(tsa, {})
            for b, v in json.loads(none_path.read_text())["birds"].items():
                anchors[tsa][(b, "none")] = v["p20"]
        if nadir_path.exists():
            anchors.setdefault(tsa, {})
            for b, v in json.loads(nadir_path.read_text())["birds"].items():
                anchors[tsa][(b, "nadir")] = v["p20"]

    long_rows = []
    for birds_path in sorted(birds_dir.glob("*/*.birds.json")):
        match = TAG.match(birds_path.name.replace(".birds.json", ""))
        if not match:
            continue
        tsa, constrained, epsilon = match.group(1), match.group(2), float(match.group(3))
        point_path = points_dir / tsa / f"tsa{tsa}-{constrained}-e{epsilon}.json"
        if not point_path.exists() or tsa not in anchors:
            continue
        point = json.loads(point_path.read_text())
        birds = json.loads(birds_path.read_text())["birds"]
        for species in SPECIES:
            long_rows.append({
                "tsa": tsa, "constrained": constrained, "epsilon": epsilon,
                "harvest": point["harvest_m3_yr"], "target_met": point["bird_target_met"],
                "species": species, "p20": birds[species]["p20"], "guild": GUILD[species],
            })
    long = pd.DataFrame(long_rows)
    if long.empty:
        return long, long

    none = {(t, s): anchors[t][(s, "none")] for t in anchors for s in SPECIES
            if (s, "none") in anchors[t]}
    long["none"] = [none[(t, s)] for t, s in zip(long.tsa, long.species)]
    ref = long.groupby(["tsa", "species"]).p20.max().to_dict()
    for t in anchors:
        for s in SPECIES:
            for key in ("none", "nadir"):
                if (s, key) in anchors[t]:
                    ref[(t, s)] = max(ref.get((t, s), 0.0), anchors[t][(s, key)])
    long["ref_max"] = [ref[(t, s)] for t, s in zip(long.tsa, long.species)]

    long["R_none"] = np.where(long.none > 0, long.p20 / long.none, np.nan)
    long["R_att"] = np.where(long.ref_max > 0, long.p20 / long.ref_max, np.nan)
    return long


def summarise(long: pd.DataFrame, cap: float) -> pd.DataFrame:
    g = long.copy()
    g["R_none_capped"] = np.minimum(g.R_none, cap)
    keys = ["tsa", "constrained", "epsilon", "harvest", "target_met"]
    wide = g.pivot_table(index=keys, columns="species", values=["R_none_capped", "R_att"], aggfunc="first")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    att_cols = [f"R_att_{s}" for s in SPECIES]
    none_cols = [f"R_none_capped_{s}" for s in SPECIES]
    wide["index_att"] = wide[att_cols].mean(axis=1)
    wide["index_ret_capped"] = wide[none_cols].mean(axis=1)
    for guild in GUILDS:
        members = [s for s in SPECIES if GUILD[s] == guild]
        wide[f"att_{guild}"] = wide[[f"R_att_{s}" for s in members]].mean(axis=1)
        wide[f"ret_{guild}"] = wide[[f"R_none_capped_{s}" for s in members]].mean(axis=1)
    return wide


def envelope(frame: pd.DataFrame, value: str, bins: int = 10) -> pd.DataFrame:
    out = []
    for tsa, g in frame.groupby("tsa"):
        if len(g) < 5:
            continue
        edges = np.unique(np.quantile(g.harvest, np.linspace(0, 1, bins + 1)))
        for low, high in zip(edges[:-1], edges[1:]):
            chunk = g[(g.harvest >= low) & (g.harvest <= high)]
            if chunk.empty:
                continue
            best = chunk.loc[chunk[value].idxmax()]
            out.append({"tsa": tsa, "harvest": float(chunk.harvest.mean()), "value": float(best[value])})
    return pd.DataFrame(out)


def fig_composite(d: pd.DataFrame, out: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharey=True)
    for ax, tsa in zip(axes.flat, ("41", "08", "16", "24", "40")):
        g = d[d.tsa == tsa]
        for guild in GUILDS:
            h = g[g.constrained.isin([s for s in SPECIES if GUILD[s] == guild])]
            ax.scatter(h.harvest, h.index_att, s=14, alpha=0.55,
                       color=GUILD_COLOR[guild], label=guild)
        env = envelope(g, "index_att")
        if not env.empty:
            ax.plot(env.harvest, env.value, color="black", lw=1.4, ls="--", label="upper envelope")
        ax.set_title(f"TSA {tsa}")
        ax.set_xlabel("harvest (M m³/yr)")
    for ax in axes[:, 0]:
        ax.set_ylabel("composite attainment  I")
    axes[1, 2].axis("off")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    axes[1, 2].legend(handles, labels, loc="center left", title="constrained guild")
    fig.suptitle("Composite bird attainment (mean share of each species' campaign best) vs harvest", fontsize=12)
    fig.tight_layout()
    fig.savefig(out / "f6_composite_index.png", bbox_inches="tight")
    fig.savefig(out / "f6_composite_index.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_guilds(d: pd.DataFrame, out: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharey=True)
    for ax, guild in zip(axes.flat, GUILDS):
        for tsa in ("41", "08", "16", "24", "40"):
            g = d[d.tsa == tsa]
            ax.scatter(g.harvest, g[f"att_{guild}"], s=9, alpha=0.30, color=TSA_COLOR[tsa])
            env = envelope(g, f"att_{guild}")
            if not env.empty:
                ax.plot(env.harvest, env.value, color=TSA_COLOR[tsa], lw=1.4, label=f"TSA {tsa}")
        ax.set_title(guild, color=GUILD_COLOR[guild])
        ax.set_xlabel("harvest (M m³/yr)")
    for ax in axes[:, 0]:
        ax.set_ylabel("guild attainment  I_g")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Guild attainment vs harvest (equal weight within guild)", fontsize=12)
    fig.tight_layout()
    fig.savefig(out / "f7_guild_indices.png", bbox_inches="tight")
    fig.savefig(out / "f7_guild_indices.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--birds", type=Path, required=True)
    parser.add_argument("--none", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cap", type=float, default=2.0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    long = build(args.points, args.birds, args.none)
    if long.empty:
        print("no joined points; is the birds pass complete?")
        return 1
    wide = summarise(long, args.cap)
    wide.to_csv(args.out / "composite_points.csv", index=False)
    long.to_csv(args.out / "composite_long.csv", index=False)
    fig_composite(wide, args.out)
    fig_guilds(wide, args.out)
    print(f"points {len(wide)}  tsas {wide.tsa.nunique()}")
    print(wide.groupby("tsa").agg(n=("index_att", "size"), att_min=("index_att", "min"),
                                  att_med=("index_att", "median"), att_max=("index_att", "max")).round(3).to_string())
    print("\nguild attainment:")
    print(wide[[f"att_{g}" for g in GUILDS]].agg(["min", "median", "max"]).round(3).to_string())
    print("\nretention (capped at %.1f), for reference:" % args.cap)
    print(wide.groupby("tsa")["index_ret_capped"].agg(["min", "median", "max"]).round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
