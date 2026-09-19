"""The five layer implementations (C§5).

Deliberately empty of imports: `registry.py` imports the layer modules and is itself
imported by the probe job. The probe job installs `[spatial]` as of C-c2; what still
forbids a convenience re-export here is that the default test suite runs
`-m 'not spatial'`, and `-m` deselects AFTER collection, so a module-scope import
would drag every layer module in and break collection of the whole default suite —
their method-scoped spatial imports stay method-scoped only if nothing forces them
earlier.
"""
