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

Bird abundance enters the LP as a fixed row coefficient per (development type,
age), materialised in the model itself. Two response forms are supported:

- ``bird/coefficients.yaml`` — the legacy linear anticipation function
  ``bird = c1*swdvol + c2*hwdvol + c3*age + c4`` (kept for parity).
- ``bird/response_table.csv`` — precomputed values for any fitted response
  (linear or not), evaluated once on the planning state space. Because the row
  is a fixed coefficient, the LP stays linear in the prescription variables
  without requiring the ecological response itself to be linear in covariates.

Resolution order is response table first, else coefficients. Because the row is
part of the LP, bird series are read exactly from the LP solution — not
reconstructed from schedules afterwards.

Bird regression (native)
------------------------

The response functions are fitted **inside the engine** — ``wbi_birds.regression``
is a native Python port of the original R/SpaDES ``fitBirdBiomassModel`` logic:
kNN stand-age projection to the observation year, species-biomass scaling and
wood-type aggregation, Poisson GLM with full fit statistics (coefficients, SEs,
z, p, deviance, AIC), and stepwise-AIC selection. Optional raster covariate
sampling lives in ``wbi_birds.covariates`` (``pip install wbi-birds[covariates]``).
No R, SpaDES, or subprocess is required.

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
