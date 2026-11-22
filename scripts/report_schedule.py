#!/usr/bin/env python
"""Report a state-watch schedule: realized harvest, bird abundance, per period.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/report_schedule.py /path/to/schedule.csv

Periods default to 20 x 10 years.  The harvest level targets are read from
``--targets`` (each period's ``minimum`` on the harvest account, if present);
pass the target file used for the run so the realized column is comparable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_DATASET = Path(
    "/srv/shared-data/gep/ws4/femic/external/femic-tsa41-instance/output"
    "/patchworks_tsa41_p120/compiled-bird"
)
ACCOUNTS = (
    "product.HarvestedVolume.managed.Total.CC",
    "feature.Yield.managed.Total",
    "feature.Bird.rebnut",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schedule", type=Path)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--targets", type=Path, default=None)
    args = parser.parse_args()

    dataset = args.dataset
    cache = dataset / "cache"

    from ws4.opt.engine import OptimizeConfig, Optimizer, load_schedule_csv
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(
            years=200,
            targets_path=str(dataset / "targets-evenflow-steady-v7.yaml"),
            iterations=1,
            threads=1,
        ),
    )
    trajectory = TrackTrajectory.build(optimizer.simulator(), 200, ACCOUNTS)
    state = BlockAccountState(
        trajectory,
        sorted(int(b) for b in optimizer.simulator().fragments["block_id"].unique()),
        ACCOUNTS,
        years=200,
        period_width=10,
        skip_empty=True,
    )
    state.load_seed(cache / "seed-state.npz")
    state.set_schedule(load_schedule_csv(args.schedule))

    levels: dict[int, float] = {}
    if args.targets is not None:
        import yaml

        payload = yaml.safe_load(args.targets.read_text())
        for target in payload.get("targets", []):
            if (
                target.get("account") == ACCOUNTS[0]
                and target.get("flow") is None
                and target.get("minimum") is not None
            ):
                levels[int(target["period"])] = float(target["minimum"])

    volume = state.period_totals[:, 0]
    bird = state.period_totals[:, 2]
    print("period  harvest(M m3)  target(M m3)  pct     bird")
    for period in range(state.periods):
        target = levels.get(period + 1)
        pct = f"{volume[period] / target * 100:6.1f}%" if target else "     —"
        shown = f"{target / 1e6:11.2f}" if target else "          —"
        print(
            f"{period + 1:6d} {volume[period] / 1e6:14.2f} {shown} {pct} "
            f"{bird[period] / 1e6:7.2f}M"
        )
    mean = float(volume.mean()) / 1e6
    print(
        f"\nmean {mean:.2f}M/period = {mean / 10:.3f}M m3/yr  "
        f"min {volume.min() / 1e6:.2f}M  max {volume.max() / 1e6:.2f}M"
    )
    if levels:
        inside = sum(
            abs(volume[p - 1] - t) <= 0.1 * t for p, t in levels.items()
        )
        print(f"periods within +-10% of target: {inside}/{len(levels)}")
    print(f"bird range: {bird.min() / 1e6:.2f}M - {bird.max() / 1e6:.2f}M")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
