# Examples

Runnable, public-safe examples on packaged fixtures (no private data).

- `quickstart.ipynb` — the full chain on the fixture estate:
  ingest → fit → compile → build → bird scenario → parity. Executed in CI
  (`.github/workflows/ci.yml`, `examples` job).
- `data/` — the packaged example data:
  - `instance_template/` — fixture instance (TSA24 data-contract layout);
  - `femic_bundle/` — ws3 sections, as staged by `compile_instance`;
  - `ebd/sample_ebd.txt` — tiny EBD extract for `ingest_ebd`;
  - `reference/tsa24-s00.csv` — packaged parity reference (generated from this
    fixture chain; in the campaign the reference comes from the legacy archive —
    see `planning/parity-reference-acquisition.md`).
- `_workdir/` — created by the notebook; git-ignored.

Run:

```bash
pip install -e ".[dev,workflow,examples]"
jupyter lab examples/quickstart.ipynb
# or headless:
python -m nbconvert --to notebook --execute examples/quickstart.ipynb
```

The matching workflow graph is `workflows/wbi_example.yaml`.
