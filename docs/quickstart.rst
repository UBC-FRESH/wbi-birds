Quickstart
==========

Install (development, public lane)::

    python -m venv .venv && . .venv/bin/activate
    pip install -e ".[dev,workflow]"

``dev`` pulls the verification tooling; ``workflow`` pins FreshForge. Both lanes
are public — no private data are needed to install, test, or run the packaged
fixtures.

Verify the checkout::

    ruff format --check src tests
    ruff check src tests
    pytest

Exercise the engine on packaged fixtures (no private data)::

    pytest tests/test_forge_full_chain.py -q      # five-node FreshForge chain
    pytest tests/test_verify_parity_hook.py -q    # parity hook

Command line::

    wbi-birds --help
    wbi-birds instance validate <instance>

Next: :doc:`concepts` for the engine model, :doc:`workflows` for driving the
FreshForge graphs, and :doc:`parity` for the verification story. The real-data
lane (private eBird extract + femic model builds) is described in
:doc:`reproducibility`.
