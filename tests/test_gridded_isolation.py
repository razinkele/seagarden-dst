"""`gridded.py` is the only module outside `refresh/` that imports xarray.

Scoped to the core, NOT to `src/`: five `refresh/` modules already import it, one at
runtime (`merge.py:85`), and that is correct — `refresh/` is build-time tooling walled
off by `test_no_core_module_imports_refresh`. A `src/`-wide assertion would fail the day
it was written, which is how the first draft of the D-a design had it.
"""

import ast
import pathlib


def test_only_gridded_imports_xarray_outside_refresh():
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "seagarden_dst"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if "refresh" in path.parts or path.name == "gridded.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n.split(".")[0] in {"xarray", "rioxarray", "shapely"} for n in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"spatial-extra imports outside refresh/ and gridded.py: {offenders}"
