"""Staged even-flow continuation watcher (TSA41 first).

Stage 0: harvest level target at 100% of estimated LTSY, no flow constraint.
         Runs until the later periods reach the target and the objective stops moving.
Then:    even-flow band switched on at +/-10%, and tightened by one point per side
         (9, 8, 7, 6, 5) whenever a stage settles. Each stage warm-starts from the
         previous schedule, so the band tightens around a schedule that already has
         the volume.

Watch it live: the status line prints every --print-every iterations.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/staged_band_watch.py --dataset campaigns/.../full-landscape/tsa41 \
        --out campaigns/.../prime/tsa41-staged.csv

LTSY default: the mean-annual-increment upper bound of the managed blocks, computed
from the dataset's per-track total yield curves. Override with --ltsy (m3/yr).
"""
from __future__ import annotations

import argparse
import csv
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"
WIDTH = 10
PERIODS = 20


def mai_bound(dataset: Path, index: dict) -> tuple[float, dict[int, int]]:
    """Return the MAI upper bound (m3/yr) and the best age per track."""
    frag = pd.read_parquet(dataset / "fragments.parquet")
    feats = pd.read_parquet(dataset / "features.parquet")
    curves = pd.read_parquet(dataset / "curves.parquet")
    grid = np.arange(0, 301)
    total: dict[int, np.ndarray] = {}
    for track, rows in feats[feats.label == "feature.Yield.managed.Total"].groupby("track_id"):
        curve = curves[curves.curve_id == rows.curve_id.iloc[0]].sort_values("x")
        total[int(track)] = np.interp(grid, curve.x.to_numpy(float), curve.y.to_numpy(float),
                                      left=0.0, right=float(curve.y.iloc[-1]))
    area = frag.area_ha.to_numpy(float)
    tracks = frag.track_id.to_numpy(int)
    managed = [int(b) for b in index if index.get(b)]
    bound, best_age = 0.0, {}
    for b in managed:
        y = total.get(int(tracks[b]))
        if y is None:
            continue
        mai = y / np.maximum(grid, 1)
        k = int(np.argmax(mai))
        bound += area[b] * mai[k]
        best_age[int(tracks[b])] = k
    return bound, best_age


def rotation_seed(frag: pd.DataFrame, managed: list[int], best_age: dict[int, int]) -> dict:
    """Regulated-forest seed: spread the over-mature first cuts across one rotation.

    Blocks older than their best MAI age are ordered oldest-first and their first cut
    is spread evenly over the rotation length, so the initial profile is not a year-0
    spike. Every block is then re-cut at its rotation length until the horizon.
    """
    area = frag.area_ha.to_numpy(float)
    track = frag.track_id.to_numpy(int)
    age = frag.age.to_numpy(float)
    over: dict[int, list[int]] = {}
    for b in managed:
        rot = best_age.get(int(track[b]))
        if rot and rot > 0 and age[b] >= rot:
            over.setdefault(int(rot), []).append(int(b))
    first: dict[int, int] = {}
    for rot, group in over.items():
        group.sort(key=lambda b: -age[b])
        n = len(group)
        for i, b in enumerate(group):
            first[b] = int(i * rot / max(n, 1))
    schedule: dict[int, tuple] = {}
    for b in managed:
        rot = best_age.get(int(track[b]))
        if not rot or rot <= 0:
            continue
        year = first.get(int(b), int(np.ceil(max(rot - age[b], 0))))
        events = []
        while year < 200 and len(events) < 4:
            events.append(("CC", int(year)))
            year += rot
        if events:
            schedule[int(b)] = tuple(events)
    return schedule


def target_yaml(path: Path, ltsy_period: float, band: float | None) -> Path:
    lines = ["targets:"]
    for period in range(1, PERIODS + 1):
        lines += [
            f"- account: {HARVEST}", f"  period_width: {WIDTH}",
            f"  minimum: {ltsy_period:.1f}", "  min_weight: 1.0", "  shape: linear",
            f"  period: {period}",
        ]
    if band is not None:
        lines += [
            f"- account: {HARVEST}", "  period: 1", f"  period_width: {WIDTH}",
            "  flow: even", "  flow_start_period: 1", "  flow_end_period: 20",
                        f"  minimum: {-band:.1f}", f"  maximum: {band:.1f}",
            "  min_weight: 1000000000.0", "  max_weight: 1000000000.0",
            "  shape: non_linear",
        ]
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--ltsy", type=float, default=None, help="target m3/yr (default: MAI bound)")
    parser.add_argument("--bands", nargs="+", type=float, default=[10, 9, 8, 7, 6, 5])
    parser.add_argument("--chunk", type=int, default=200_000)
    parser.add_argument("--max-chunks", type=int, default=12)
    parser.add_argument("--print-every", type=int, default=20_000)
    parser.add_argument("--settle", type=float, default=0.005, help="relative objective change")
    parser.add_argument("--reach", type=float, default=0.98, help="later-period share of LTSY")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-rotation-seed", action="store_true",
                        help="start from an empty schedule instead of the MAI rotation seed")
    args = parser.parse_args()

    from ws4.opt.engine import OptimizeConfig, Optimizer, load_schedule_csv
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory, run_state_sa
    from ws4.opt.objective import load_targets

    dataset = args.dataset
    with (dataset / "cache" / "candidates.pkl").open("rb") as stream:
        payload = pickle.load(stream)
    index = payload.get("candidates", payload) if isinstance(payload, dict) else payload

    ltsy = args.ltsy
    best_age: dict[int, int] = {}
    if ltsy is None:
        ltsy, best_age = mai_bound(dataset, index)
        print(f"LTSY (MAI upper bound): {ltsy/1e6:.3f} M m3/yr", flush=True)
    ltsy_period = ltsy * WIDTH

    optimizer = Optimizer.from_dataset(
        dataset, OptimizeConfig(years=200, targets_path="/tmp/opencode/targets-level40.yaml",
                                iterations=1, threads=1))
    simulator = optimizer.simulator()
    blocks = sorted(int(b) for b in simulator.fragments["block_id"].unique())
    trajectory = TrackTrajectory.build(simulator, 200, (HARVEST, STOCK))
    state = BlockAccountState(trajectory, blocks, (HARVEST, STOCK),
                              years=200, period_width=WIDTH, skip_empty=False)

    schedule: dict = {}
    if not args.no_rotation_seed:
        if not best_age:
            _, best_age = mai_bound(dataset, index)
        frag = pd.read_parquet(dataset / "fragments.parquet")
        schedule = rotation_seed(frag, [int(b) for b in index if index.get(b)], best_age)
        print(f"rotation seed: {len(schedule):,} blocks, "
              f"{sum(len(v) for v in schedule.values()):,} events", flush=True)
        state.set_schedule({b: v for b, v in schedule.items()})
        values = state.period_totals[:, 0] / 1e6
        print(f"seed profile: mean {values.mean():.3f} later5 {values[-5:].mean():.3f} "
              f"[{values.min():.2f},{values.max():.2f}] M/period", flush=True)
    if args.out.exists() and schedule:
        resumed = load_schedule_csv(args.out)
        if len(resumed) >= len(schedule):
            schedule = resumed
            state.set_schedule(schedule)
            print(f"resuming from {args.out} ({len(schedule):,} blocks)", flush=True)

    log_path = args.log or args.out.with_suffix(".stages.csv")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log_path.exists()
    log = log_path.open("a", newline="")
    writer = csv.DictWriter(log, fieldnames=["stage", "band", "chunk", "iterations", "objective",
                                             "level_mean", "level_min", "level_max",
                                             "later_mean", "band_violations", "seconds"])
    if new_log:
        writer.writeheader()

    stage_names = ["level"] + [f"band{int(b)}" for b in args.bands]
    all_bands = [None] + list(args.bands)
    yaml_path = Path(f"/tmp/opencode/staged-{dataset.name}.yaml")

    for stage_name, band in zip(stage_names, all_bands):
        target_yaml(yaml_path, ltsy_period, band)
        targets = load_targets(yaml_path)
        print(f"\n=== {stage_name} (band={band}) target {ltsy_period/1e6:.2f} M m3/period", flush=True)
        previous = None
        for chunk in range(1, args.max_chunks + 1):
            started = time.perf_counter()

            def on_step(it: int, _state, best: float, chunk=chunk) -> None:
                if it % args.print_every:
                    return
                values = state.period_totals[:, 0] / 1e6
                print(f"  {stage_name} chunk {chunk} it {it:>8,} obj {best:12.4g} "
                      f"level {values.mean():6.3f} [{values.min():6.2f},{values.max():6.2f}] M/period",
                      flush=True)

            schedule, objective = run_state_sa(
                state, index, targets, iterations=args.chunk,
                initial=schedule or None, seed=args.seed, on_step=on_step,
            )
            values = state.period_totals[:, 0] / 1e6
            later = float(values[-5:].mean())
            target = ltsy_period / 1e6
            reference = values[-1]  # engine default: terminal period
            rel = 100.0 * (values - reference) / reference
            violations = int((np.abs(rel) > (band if band is not None else 1e9)).sum())
            elapsed = time.perf_counter() - started
            row = {"stage": stage_name, "band": band, "chunk": chunk,
                   "iterations": args.chunk, "objective": round(float(objective), 3),
                   "level_mean": round(float(values.mean()), 4), "level_min": round(float(values.min()), 4),
                   "level_max": round(float(values.max()), 4), "later_mean": round(later, 4),
                   "band_violations": violations, "seconds": round(elapsed, 1)}
            writer.writerow(row)
            log.flush()
            print(f"  {stage_name} chunk {chunk} done: obj {objective:.4g} level {values.mean():.3f} "
                  f"later5 {later:.3f}/{target:.3f} outside ±{band if band is not None else '—'}: "
                  f"{violations} ({elapsed:.0f}s)", flush=True)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([{"block_id": b, "treatment": t, "offset": o}
                          for b, events in schedule.items() for t, o in events],
                         columns=["block_id", "treatment", "offset"]).to_csv(args.out, index=False)

            settled = previous is not None and abs(objective - previous) <= args.settle * max(abs(previous), 1e-9)
            previous = objective
            if band is None:
                reached = later >= args.reach * target
                if settled and reached:
                    print(f"  level stage settled at {values.mean():.3f} M/period, later5 {later:.3f}", flush=True)
                    break
            elif settled:
                break
        else:
            print(f"  {stage_name}: max chunks reached without settling", flush=True)

    log.close()
    print(f"\nschedule: {args.out}\nstage log: {log_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
