# wbi-birds

Simulation engine for the **WBI birds study** — ε-constraint tradeoff analysis
between even-flow harvesting and multi-species bird abundance, built on
[`ws3`](https://github.com/UBC-FRESH/ws3).

> Companion manuscript: [`UBC-FRESH/wbi-birds-manuscript`](https://github.com/UBC-FRESH/wbi-birds-manuscript)
> (target journal: *Environmental Modelling & Software*).

## What it does

- Builds ws3 forest-estate models for five timber supply areas (TSAs 08/16/24/40/41, northeastern British Columbia)
- Embeds habitat-association ("anticipation") functions for a suite of boreal landbird species and guilds
- Runs the ε-constraint scenario grid between maximum even-flow harvest and maximum bird abundance
- Produces the Pareto tradeoff frontiers, marginal opportunity-cost curves, and campaign diagnostics used by the manuscript

## Status

`v1.0.0` — engine phases E-P1–E-P6 complete (pipeline, bird module, verification
framework, docs, examples). The real-data campaign lane (private eBird extract,
femic model builds) and the legacy parity run are gated on external inputs; the
manuscript's full scope and schedule live in
`UBC-FRESH/wbi-birds-manuscript` → `ROADMAP.md` (v2); engine phases in this repo's `ROADMAP.md`.

## Install (development)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]
pytest
wbi-birds --help
```

## Bootstrap (self-reproduction)

Two lanes: a **public lane** that installs and runs from packaged fixtures (no
private data), and a **campaign lane** for the manuscript runs (private eBird
extract + femic model builds). The public lane is the acceptance test for every
release.

Public lane (fresh environment, verified at `v1.0.0`):

```bash
git clone https://github.com/UBC-FRESH/wbi-birds
cd wbi-birds
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,workflow,examples]"
pytest -q
python -m nbconvert --to notebook --execute examples/quickstart.ipynb
```

Campaign lane (team; sibling `femic` checkout + private data):

```bash
pip install -e ../femic        # model building/running incl. ws3
git submodule update --init external/wbi-ebird-data && datalad get -r external/wbi-ebird-data

freshforge run workflows/wbi_pipeline.yaml --workdir . --namespace tsa40 \
  --evidence results/workflow/tsa40-evidence.json
```

## Reproduction boundary

- Raw eBird data are **not** redistributed (see the manuscript repo's `planning/ebird-data-request*.md`).
- Derived, shareable instance inputs are versioned snapshots (Zenodo, planned at release).

## License

MIT. Cite via `CITATION.cff` (`v1.0.0`); the Zenodo DOI is added once the
Zenodo–GitHub integration is enabled for this repository.
