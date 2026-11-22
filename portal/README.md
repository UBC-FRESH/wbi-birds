# WBI Birds portal

Open, reproducible explorer for the five-TSA wood supply × bird abundance campaign.

- **Land base** — per-TSA area, THLB calibration to TSR-reported values, age structure.
- **Bird models** — methods, coefficient tables, covariate distributions, response curves, diagnostics.
- **Tradeoffs** — harvest at equal relative bird attainment (aspatial vs spatial), same-schedule impact, verdict.
- **Maps** — full-resolution block geometry as vector tiles; management status and harvest-year layers.

Static UI (vendored ECharts + MapLibre, no build step) with an optional FastAPI shell.

## Run

```bash
./run.sh            # default 0.0.0.0:8132
PORT=8133 ./run.sh
```

Health: `GET /api/health`. Data contract: `GET /api/manifest`.

The live deployment is `/srv/shared-data/gep/jupyterhub16-projects/wbi-portal`
(public `https://wbi-birds.01101.dev`, Cloudflare Access). `./deploy.sh` syncs the tracked
source here into that directory; generated data and tiles are left in place.

## Generated artifacts (not committed)

| path | generator | content |
|---|---|---|
| `ui/data/*.json` | `build_data.py` | manifest, land base, fits, frontiers |
| `ui/tiles/tsaXX/` | `build_tiles.py` | directory vector tiles, z5–z14 |

`build_data.py` reads `/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11`
(compiled datasets, bird fits, prime schedules, campaign CSVs). `build_tiles.py` needs a
local `tippecanoe` binary (see the campaign planning record for the build command).

Raw eBird records are never exposed; only fitted coefficients, diagnostics, and aggregates.
