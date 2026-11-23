"""Evaluate all guilds on the saved mature-conifer gradient schedules and plot responses."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_model20 import SpatialBird20

C = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11")
D = C / "full-landscape/tsa41"
GEOM = Path("/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa41-instance/data/ria_vri_vclr1p_checkpoint7.feather")
FITS = C / "bird-fits/knn-v0-nine-species-spatial-local.json"
SCHED = C / "dual/mature-schedules"
OUT = Path("/srv/shared-data/gep/wbi-birds/fvsbc-work/guild-response-mature.csv")
IMG = Path("/srv/shared-data/gep/wbi-birds/wbi-birds-manuscript/images/ws4-2026-11/fig_guild_response.pdf")
GUILDS = ("mature_conifer", "mixedwood", "early_seral", "cavity")
HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"

from ws4.opt.engine import OptimizeConfig, Optimizer
from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

opt = Optimizer.from_dataset(D, OptimizeConfig(years=200, targets_path="/tmp/opencode/targets-level40.yaml", iterations=1, threads=1))
sim = opt.simulator()
blocks = sorted(int(b) for b in sim.fragments["block_id"].unique())
accounts = (HARVEST, STOCK, *[f"feature.Bird.{g}" for g in GUILDS])
state = BlockAccountState(TrackTrajectory.build(sim, 200, accounts), blocks, accounts, years=200, period_width=10, skip_empty=False)
idx = {a: accounts.index(a) for a in accounts}
state.set_schedule({})
asp = {g: float(state.period_totals[-1, idx[f"feature.Bird.{g}"]]) for g in GUILDS}
sp = {g: SpatialBird20(D, GEOM, FITS, guild=g) for g in GUILDS}
spb = {g: float(sp[g].totals()[g]) for g in GUILDS}

def last(events):
    ys = [int(y) for _, y in events if int(y) <= 199]
    return float(max(ys)) if ys else None

rows = []
KEEP = {"0.80","0.83","0.86","0.89","0.92","0.95","0.98","1.00"}
for p in sorted(SCHED.glob("*-schedule.csv")):
    mode, att = p.name.replace("-schedule.csv", "").split("-")
    if att not in KEEP:
        continue
    d = pd.read_csv(p)
    sched = {}
    for b, g in d.groupby("block_id"):
        sched[int(b)] = tuple((str(t), int(o)) for t, o in zip(g["treatment"], g["offset"]))
    state.set_schedule(sched)
    h = float(state.period_totals[:, idx[HARVEST]].mean()) / 10 / 1e6
    sps = {b: y for b, ev in sched.items() if (y := last(ev)) is not None}
    for g in GUILDS:
        a = float(state.period_totals[-1, idx[f"feature.Bird.{g}"]])
        sp[g].reset(sps)
        s = float(sp[g].totals()[g])
        rows.append(dict(mode=mode, attainment=float(att), harvest=round(h, 3), guild=g,
                         aspatial=a / asp[g], spatial=s / spb[g]))
    print(p.name, round(h, 2), flush=True)

df = pd.DataFrame(rows)
df.to_csv(OUT, index=False)
print("wrote", OUT, len(df))

fig, axes = plt.subplots(2, 2, figsize=(8.0, 6.0), sharex=True, sharey=True)
for ax, g in zip(axes.flat, GUILDS):
    d = df[df.guild == g]
    for mode, color in (("aspatial", "#b2182b"), ("spatial", "#2166ac")):
        m = d[d["mode"] == mode].sort_values("harvest")
        ax.plot(m.harvest, 100 * m[mode], "o-", color=color, markersize=3, linewidth=1, label=mode)
    ax.axhline(100, color="0.5", linewidth=0.6, linestyle=":")
    ax.set_title(g.replace("_", " "), fontsize=9)
    ax.grid(color="0.92", linewidth=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
for ax in axes[-1]:
    ax.set_xlabel("Realized harvest (M m$^3$ yr$^{-1}$)")
for ax in axes[:, 0]:
    ax.set_ylabel("Guild abundance (% of no-harvest baseline)")
axes.flat[0].legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(IMG)
fig.savefig(IMG.with_suffix(".png"), dpi=200)
print("wrote", IMG)
