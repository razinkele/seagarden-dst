"""The five layer implementations (C§5).

Deliberately empty of imports: `registry.py` imports the layer modules and is itself
imported by the probe job, which installs the bare package. A convenience re-export
here would drag every layer module — and their method-scoped spatial imports stay
method-scoped only if nothing forces them earlier.
"""
