"""Build a full-landscape compiled dataset from a femic checkpoint and a Patchworks XML.

The recipe reproduces the four existing full-landscape datasets: fragments are every
polygon in the checkpoint, operability is the documented THLB net-down
(mean ``thlb_raw >= 50``), and the Patchworks p120 model supplies the per-species yields.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu python scripts/build_full_landscape.py \
      --checkpoint /tmp/opencode/tsa24-checkpoint7.feather \
      --xml tmp/ws4-pilot/patchworks-tsa24-thlb50/forestmodel.xml \
      --tsa 24 --out campaigns/.../full-landscape/tsa24

Area units differ between femic exports: TSA41/16/40/08 store hectares, the TSA24
checkpoint stores square metres.  The unit is detected and reported; verify the printed
managed area against the documented land base before using the dataset.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = (
    "au", "PROJ_AGE_1", "POLYGON_AREA", "thlb_raw",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--xml", type=Path, required=True)
    parser.add_argument("--tsa", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--csv-out", type=Path, default=None)
    parser.add_argument("--thlb-min", type=float, default=50.0)
    parser.add_argument("--no-build", action="store_true", help="write the CSV only")
    args = parser.parse_args()

    frame = pd.read_feather(args.checkpoint, columns=list(COLUMNS))
    area = frame["POLYGON_AREA"].to_numpy(float)
    unit = "m2" if float(np.median(area)) > 100.0 else "ha"
    area_ha = area / 1e4 if unit == "m2" else area

    age = frame["PROJ_AGE_1"].to_numpy(float)
    age = np.where(np.isfinite(age), age, 0.0).astype(np.int64)
    thlb = frame["thlb_raw"].to_numpy(float)
    managed = thlb >= args.thlb_min

    fragments = pd.DataFrame({
        "FRAGMENT_I": np.arange(len(frame), dtype=np.int64),
        "BLOCK": np.arange(len(frame), dtype=np.int64),
        "AREA_HA": area_ha,
        "F_AGE": age,
        "AU": frame["au"].to_numpy(np.int64),
        "IFM": np.where(managed, "managed", "unmanaged"),
        "ORIGIN": "natural",
        "SILV_STATE": "baseline",
        "RETENTION": 0.0,
        "TSA": args.tsa,
        "CFS_ECOZON": 0,
    })

    csv_out = args.csv_out or Path(f"/tmp/opencode/tsa{args.tsa}-full-fragments.csv")
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fragments.to_csv(csv_out, index=False)
    print(f"areas detected as {unit}; wrote {csv_out} ({len(fragments):,} fragments)")
    print(f"managed {int(managed.sum()):,} fragments, {area_ha[managed].sum()/1e6:.3f} M ha; "
          f"unmanaged {int((~managed).sum()):,}, {area_ha[~managed].sum()/1e6:.3f} M ha")

    if args.no_build:
        return 0

    from ws4.build.compiler import build_canonical_dataset

    build_canonical_dataset(args.xml, csv_out, args.out)
    print(f"compiled dataset: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
