Parity
======

Legacy RBNU / 5-TSA simulation outputs are compared against engine results
through a long-format reference table:

=============== ============ ==================== ======= ======
management_unit scenario_id  metric               period  value
=============== ============ ==================== ======= ======
TSA24           tsa24-s00    harvest_volume_m3    1       123.4
=============== ============ ==================== ======= ======

Tolerance policy
----------------

A record passes when

.. math::

   |engine - reference| \le abs\_tol + rel\_tol \cdot |reference|

with per-metric defaults (``rel_tol = 1e-3``) in ``wbi_birds.parity``. Missing
engine rows, missing reference rows, and tolerance failures are explicit failure
reasons in the comparison records. Final tolerance values are adjudicated against
the legacy numbers before any manuscript claim.

Running a comparison
--------------------

Inside a FreshForge graph, the ``verify_parity`` node compares everything under
``<instance>/results/scenarios/**`` against the ``reference`` parameter and
writes ``<instance>/results/parity/<label>-parity.{json,md}``; mismatches raise
``parity.failed`` warnings, and ``strict: true`` fails the node
(``parity.strict``).

Standalone:

.. code-block:: console

   python scripts/parity_check.py <instance> <reference.csv> \
       --label <mu> [--strict]

Acquisition of the legacy reference (archive/re-run, export checklist, unit and
scope checks) is documented in ``planning/parity-reference-acquisition.md``.
