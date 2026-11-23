"""Guild abundance vs realized harvest on the existing multi-entry campaign schedules."""
from __future__ import annotations
import csv, hashlib, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_model20 import SpatialBird20

C = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11")
D = C / "full-landscape/tsa41"
GEOM = Path("/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa41-instance/data/ria_vri_vclr1p_checkpoint7.feather")
FITS = C / "bird-fits/scanfi-240m-nine-species-spatial.json"
GUILDS = ("mature_conifer", "mixedwood", "early_seral", "cavity")
HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"

from ws4.opt.engine import OptimizeConfig, Optimizer
from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

optimizer = Optimizer.from_dataset(D, OptimizeConfig(years=200, targets_path="/tmp/opencode/targets-level40.yaml", iterations=1, threads=1))
sim = optimizer.simulator()
blocks = sorted(int(b) for b in sim.fragments["block_id"].unique())
accounts = (HARVEST, STOCK, *[f"feature.Bird.{g}" for g in GUILDS])
traj = TrackTrajectory.build(sim, 200, accounts)
state = BlockAccountState(traj, blocks, accounts, years=200, period_width=10, skip_empty=False)
idx = {a: accounts.index(a) for a in accounts}

state.set_schedule({})
asp_base = {g: float(state.period_totals[-1, idx[f"feature.Bird.{g}"]]) for g in GUILDS}
print("aspatial baselines", {g: round(v) for g, v in asp_base.items()}, flush=True)

spatial = {g: SpatialBird20(D, GEOM, FITS, guild=g) for g in GUILDS}
sp_base = {g: float(spatial[g].totals()[g]) for g in GUILDS}
print("spatial baselines", {g: round(v) for g, v in sp_base.items()}, flush=True)

# unique schedule files
seen = set(); schedules = []
for p in sorted((C / "dual-scanfi-240m/mature-schedules").glob("*-schedule.csv")):
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    if h in seen: continue
    seen.add(h); schedules.append(p)
print("schedules", len(schedules), flush=True)

def last_year(events):
    years = [int(y) for _, y in events if int(y) <= 199]
    return float(max(years)) if years else None

rows = []
for p in schedules:
    d = pd.read_csv(p)
    sched = {}
    for b, g in d.groupby("block_id"):
        sched[int(b)] = tuple((str(t), int(o)) for t, o in zip(g["treatment"], g["offset"]))
    state.set_schedule(sched)
    harvest = float(state.period_totals[:, idx[HARVEST]].mean()) / 10 / 1e6
    sp_sched = {b: last_year(ev) for b, ev in sched.items()}
    sp_sched = {b: y for b, y in sp_sched.items() if y is not None}
    for g in GUILDS:
        a = float(state.period_totals[-1, idx[f"feature.Bird.{g}"]])
        spatial[g].reset(sp_sched)
        s = float(spatial[g].totals()[g])
        rows.append(dict(schedule=p.name, harvest=round(harvest, 4), guild=g,
                         aspatial=a / asp_base[g], spatial=s / sp_base[g],
                         events_per_block=round(len(d) / d.block_id.nunique(), 2)))
    print(p.name, "harvest", round(harvest, 3), flush=True)

out = C / "dual-scanfi-240m/tsa41-guild-response.csv"
pd.DataFrame(rows).to_csv(out, index=False)
print("wrote", out, len(rows), flush=True)
