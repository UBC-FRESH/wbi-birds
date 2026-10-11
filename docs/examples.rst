Examples
========

The packaged example walks the full chain on fixture data (no private data):
**ingest → fit → compile → build → scenario → parity**.

- Notebook: ``examples/quickstart.ipynb``
- Graph: ``workflows/wbi_example.yaml``
- Data: ``examples/data/`` — fixture estate (TSA24), ws3 sections, a small EBD
  extract, provided coefficients, and a packaged reference table for the parity
  check
- Work directory: ``examples/_workdir/`` (created by the notebook; git-ignored)

.. code-block:: console

   pip install -e ".[dev,workflow,examples]"
   python -m nbconvert --to notebook --execute examples/quickstart.ipynb

CI executes the notebook on every change (``examples`` job in
``.github/workflows/ci.yml``).
