Workflows (FreshForge)
======================

The engine ships a FreshForge provider (``wbi``) whose node types execute the
pipeline steps. Graphs live in ``workflows/``; execution records and evidence
manifests are the run contract.

Node types
----------

.. list-table::
   :header-rows: 1

   * - Node
     - Executes
   * - ``ingest_ebd``
     - Filters the private EBD extract to the species suite; writes derived
       tables + SHA256 provenance sidecar.
   * - ``fit_antifunction``
     - Stages externally fitted coefficients (``mode: provided``) or fits them
       natively (``mode: poisson``) into the instance.
   * - ``compile_instance``
     - Stages femic-produced ws3 sections into the instance (data contract).
   * - ``build_model``
     - Builds the ws3 forest-estate model.
   * - ``run_scenarios``
     - Runs an ε-constraint scenario (harvest objective, optional bird row via
       ``bird_species`` / ``measure_scope``) and writes the result table.
   * - ``compute_frontiers``
     - Pareto frontier + marginal opportunity-cost metrics from scenario results.
   * - ``verify_parity``
     - Compares instance results against a legacy reference table
       (see :doc:`parity`).
   * - ``analyze_frontiers``
     - Analysis tables, figures, claims map.

Running a graph
---------------

.. code-block:: console

   python -m freshforge run workflows/wbi_pipeline.yaml \
       --workdir <workdir> --json --evidence <evidence.json>

``--workdir`` is the base directory the graph's relative paths resolve against;
``--evidence`` writes the machine-readable run manifest (inputs, outputs,
artifacts, diagnostics).

Shipped graphs:

- ``workflows/wbi_pipeline.yaml`` — the full pipeline graph.
- ``workflows/wbi_pipeline_template.yaml`` — parameterised template for per-MU
  runs (cases in ``workflows/wbi_mu_matrix.yaml``).
- ``workflows/wbi_smoke_fixture.yaml`` — fixture smoke graph (packaged data
  only); the executable end-to-end example is
  ``tests/test_forge_full_chain.py`` (ingest → fit → compile → build → bird
  scenario), which constructs the corresponding workdir from ``tests/fixtures``.

Composition with femic
----------------------

Model-building inputs come from femic (``femic.ws3_bridge``): the engine consumes
staged Woodstock sections and never re-implements model construction. The
coupling is file contracts + providers only — see ``planning/femic-map.md``.
