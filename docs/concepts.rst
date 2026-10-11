Concepts
========

What the engine computes
------------------------

For each management unit the engine builds a ws3 forest-estate model and runs an
ε-constraint scenario grid between maximum even-flow harvest and maximum bird
abundance. Results are per-scenario tables of harvest volume and bird abundance
by period, from which Pareto frontiers and marginal opportunity-cost metrics are
derived.

Management units (TSAs) are the unit of analysis and computation: one instance
per TSA, one frontier per TSA. There is deliberately no cross-TSA aggregation —
the decision space has no real-world analogue for it.

The data contract
-----------------

An *instance* is a self-contained directory (the engine's unit of computation):

- ``config/`` — run configuration (management unit, model harvest actions, …)
- ``inputs/ws3/`` — Woodstock sections for the unit (staged by ``compile_instance``)
- ``bird/`` — coefficients and derived (ingested) bird tables
- ``results/`` — scenario tables, parity reports, curated release outputs

The normative layout lives in ``planning/data-contract.md`` in the repository.

Bird anticipation row
---------------------

Bird abundance enters the LP as a linear *anticipation row* per development type
(age-based), materialised in the model itself:

.. math::

   \mathrm{bird} = c_1 \cdot \mathrm{swdvol} + c_2 \cdot \mathrm{hwdvol}
   + c_3 \cdot \mathrm{age} + c_4

with per-species coefficients fitted from eBird observations against forest
attributes (``provided`` mode: the manuscript's R lineage; ``poisson`` mode: the
engine-native MLE). Because the row is part of the LP, bird series are read
exactly from the LP solution — not reconstructed from schedules afterwards.

Scenario semantics
------------------

- Objective: harvest volume expression (e.g. ``totvol * 0.85``).
- Constraint: the ε-constraint row (e.g. ``bird`` measured at harvest scope, or at
  landscape scope when bird totals are the constrained quantity).
- Even-flow ε: optional flow-tolerance constraint; ``null`` disables it.

The solver is HiGHS by default (``ws3.opt.SOLVER_HIGHS``); Gurobi is an optional
switch. The solver and its version are recorded in every scenario's provenance.

The B3 experiment
-----------------

B3 contrasts a fixed habitat-only reserve network against integrated
ε-constraints at matched bird targets, comparing harvest cost. See
``wbi_birds.b3`` and the manuscript roadmap for the experiment definition.
