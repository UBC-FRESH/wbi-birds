Reproducibility
===============

Every result-affecting run records the release/solver provenance in the result
metadata. The authoritative, living document is
``results/REPRODUCIBILITY.md`` in the repository; this page summarises it.

Verification
------------

.. code-block:: console

   ruff format --check src tests
   ruff check src tests
   pytest
   sphinx-build -b html docs docs/_build/html -W

CI runs the same steps (``.github/workflows/{ci,docs}.yml``). The docs site is
published to GitHub Pages from ``main``.

Two data lanes
--------------

- **Public lane** (this package): install, tests, and the fixture pipeline run
  from packaged data only. No private data are needed, and raw eBird data are
  never redistributed.
- **Real-data lane**: private eBird extract (request runbook in the manuscript
  repository), coefficients, and femic model-build bundles with one instance per
  management unit. See ``planning/data-contract.md`` and
  ``workflows/wbi_mu_matrix.yaml``.

Fixtures vs headline results
----------------------------

The packaged fixtures exercise every engine capability end to end; headline
manuscript results are produced by the real-data lane and released with tags.
The parity framework (:doc:`parity`) is the bridge: engine results are checked
against legacy outputs within recorded tolerances before claims are made.
