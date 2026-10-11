# wbi-birds

Simulation engine for the **WBI birds study** — ε-constraint tradeoff analysis
between even-flow harvesting and multi-species bird abundance, built on
[`ws3`](https://github.com/UBC-FRESH/ws3).

> Companion manuscript: [`UBC-FRESH/wbi-birds-2021`](https://github.com/UBC-FRESH/wbi-birds-2021)
> (target journal: *Environmental Modelling & Software*).

## What it does

- Builds ws3 forest-estate models for five timber supply areas (TSAs 08/16/24/40/41, northeastern British Columbia)
- Embeds habitat-association ("anticipation") functions for a suite of boreal landbird species and guilds
- Runs the ε-constraint scenario grid between maximum even-flow harvest and maximum bird abundance
- Produces the Pareto tradeoff frontiers, marginal opportunity-cost curves, and campaign diagnostics used by the manuscript

## Status

`v0.1.0a1` — scaffold (Phase E-P1). The manuscript's full scope and schedule live in
`UBC-FRESH/wbi-birds-2021` → `ROADMAP.md` (v2); engine phases in this repo's `ROADMAP.md`.

## Install (development)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]
pytest
wbi-birds --help
```

## Bootstrap (self-reproduction)

Target bootstrap for a fresh environment (final acceptance at E-P6; two-lane data model — see `planning/workflow-blueprint.md`):

```bash
# 1. pinned environment: engine + forest-estate control plane + workflow layer
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]          # engine (includes the freshforge pin)
pip install -e ../femic        # femic: model building/running incl. ws3 (sibling checkout)

# 2. data lane (choose one)
#    public lane — released derived inputs snapshot (Zenodo DOI at release); no private access needed
#    team lane   — private annex data
git submodule update --init external/wbi-ebird-data && datalad get -r external/wbi-ebird-data

# 3. run the pipeline per management unit
freshforge plan workflows/wbi_pipeline.yaml
freshforge run  workflows/wbi_pipeline.yaml --workdir . --namespace tsa40 \
  --evidence results/workflow/tsa40-evidence.json
```

## Reproduction boundary

- Raw eBird data are **not** redistributed (see the manuscript repo's `planning/ebird-data-request*.md`).
- Derived, shareable instance inputs are versioned snapshots (Zenodo, planned at release).

## License

MIT. Cite via `CITATION.cff` once `v1.0.0` is released (Zenodo DOI to be added).
