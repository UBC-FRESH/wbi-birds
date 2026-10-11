Command-line interface
======================

The engine ships two entry points.

``wbi-birds``
-------------

.. code-block:: console

   wbi-birds --help
   wbi-birds instance validate <instance>

``instance validate`` checks an instance directory against the data contract and
reports errors/warnings with paths.

``freshforge`` (workflow layer)
-------------------------------

.. code-block:: console

   python -m freshforge run <graph.yaml> --workdir <dir> --json --evidence <file.json>
   python -m freshforge providers

The ``wbi`` provider is discovered via the ``freshforge.providers`` entry point
when the ``workflow`` extra is installed. See :doc:`workflows`.

``scripts/parity_check.py``
---------------------------

.. code-block:: console

   python scripts/parity_check.py <instance> <reference.csv> --label <name> [--strict]

See :doc:`parity`.
