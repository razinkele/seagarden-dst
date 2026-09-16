"""Package C refresh tooling.

Build-time only. Nothing here may be imported by the model core, and nothing here
may import from it — `tests/test_refresh_isolation.py` asserts both directions.
That boundary is what keeps the `spatial` extra out of the runtime install, which
is what keeps the tool reconstructible to 2034 (design section 4).
"""
