"""Whether a dataset still exists, at the version the manifest publishes (C§8.2).

This replaces an HTTP HEAD against a product landing page, which could not see
either event the monthly job exists to catch. A landing page returns 200 long after
the `dataset_id` behind it is retired, and it says nothing at all about versions.

**`describe()` needs no credential.** It accepts no `username`, `password` or
`credentials_file` — `get()` and `subset()` accept all three — and reads no cached
credential file. The catalogue is public. `source-probe.yml` passed two Copernicus
secrets until C-c2 struck them; nothing had ever read them.

**`copernicusmarine` is imported only inside `_default_describe`, i.e. only on the
real path.** The probe job installs `[spatial]` as of C-c2, so the old reason (a
bare install) is gone — but the default test suite runs `-m 'not spatial'`, `-m`
deselects after collection, and CI's default job runs a bare `pytest -q` with no
spatial extra installed at all. This file's unmarked tests drive `dataset_status`
entirely through an injected `describe`, so they must never need
`copernicusmarine` to be importable, even transitively — which is why
`DatasetNotFound` is matched by name (`_is_dataset_not_found`) rather than
imported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seagarden_dst.refresh.layer import ProbeStatus


class DescribeCallable(Protocol):
    """What `dataset_status` calls. The injection seam every test uses."""

    def __call__(self, **kwargs: Any) -> Any: ...


def _default_describe() -> DescribeCallable:
    """Resolve the real `describe`, importing inside the call."""
    import copernicusmarine

    return copernicusmarine.describe


def _served_versions(catalogue: Any) -> list[str]:
    """Flatten `products -> datasets -> versions[].label`.

    A `dataset_id` lookup returns one product holding one dataset, but the nesting
    is read generically so a catalogue that answers with more does not silently
    report only the first.
    """
    return [
        version.label
        for product in catalogue.products
        for dataset in product.datasets
        for version in dataset.versions
    ]


def _is_dataset_not_found(error: BaseException) -> bool:
    """Whether `error` is copernicusmarine's `DatasetNotFound`, matched by NAME.

    By name and not by `isinstance` against an imported class, because this
    module must classify the exception in an environment where copernicusmarine
    is not installed: CI's default job installs no spatial extra and runs the
    unmarked tests, and an import here — even inside the function — made that job
    red. Only `copernicusmarine.describe` is ever called through the seam, so a
    foreign class that happens to share the name is not a case this code meets.
    A spatial-marked test asserts the REAL class still matches, so an upstream
    rename is caught by the spatial job rather than reported as `unreachable`.
    """
    return any(cls.__name__ == "DatasetNotFound" for cls in type(error).__mro__)


def dataset_status(
    dataset_id: str,
    expected_version: str,
    *,
    describe: DescribeCallable | None = None,
) -> tuple[ProbeStatus, str]:
    """Ask the catalogue about one dataset. Returns `(status, detail)`, never raises.

    Four outcomes, deliberately distinct — the operator reading a red monthly job
    needs to tell a retired dataset (find a new source) from a drifted version
    (correct the manifest) from a network error (retry):

    - `ok` — the dataset exists and serves `expected_version`.
    - `absent` — `DatasetNotFound`. The dataset id no longer resolves.
    - `version_drift` — the dataset exists but no longer serves the version the
      manifest publishes. The provenance we ship has stopped being true.
    - `unreachable` — anything else, network included.

    Membership rather than latest-equality: C§8.2 asks 'is the provenance we publish
    still true', and a dataset that serves 202303 alongside a newer 202501 is still
    serving what the manifest recorded. A probe demanding the newest would go red on
    every reprocessing, which is an upgrade decision for a human, not a fault.
    """
    call = describe if describe is not None else _default_describe()

    try:
        catalogue = call(dataset_id=dataset_id, disable_progress_bar=True)
    except Exception as error:  # noqa: BLE001 - one dead source must not fail the job
        if _is_dataset_not_found(error):
            return "absent", f"dataset absent from catalogue: {dataset_id} ({error})"
        return "unreachable", f"unreachable: {error}"

    served = _served_versions(catalogue)
    if expected_version in served:
        return "ok", f"{dataset_id} serves version {expected_version}"
    return (
        "version_drift",
        f"{dataset_id} no longer serves the version the manifest records: "
        f"manifest says {expected_version}, catalogue serves {served}",
    )
