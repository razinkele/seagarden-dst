"""The artifact's schema and its read side — importable by the model core.

C§4.3 requires that "D and C1 validate the same way C wrote it", and C§6.1 puts the
checksum refusal in the READER. Package D is that reader, so `Manifest`, `sha256_of`
and `load_pair` cannot live behind `refresh/`'s import boundary: Task 6's isolation
test forbids any core module importing `refresh`, so D would have to turn that test
red or keep a second copy of the schema — and a second copy is how the manifest and
the reader drift apart.

The split follows the DEPENDENCY, not the package name. Everything here needs only
pydantic, stdlib and numpy. `write_pair` takes an `xr.Dataset` and stays in
`refresh/writer.py`, where the xarray dependency belongs.
"""

from .grid import GridSpec
from .manifest import (
    AbsentField,
    Archive,
    Derivation,
    LayerProvenance,
    Manifest,
)
from .pair import check_declaration, load_pair, sha256_of

__all__ = [
    "AbsentField",
    "Archive",
    "Derivation",
    "GridSpec",
    "LayerProvenance",
    "Manifest",
    "check_declaration",
    "load_pair",
    "sha256_of",
]
