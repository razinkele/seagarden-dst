"""Whether a dataset still exists, at the version the manifest publishes (C§8.2).

This replaces an HTTP HEAD against a product landing page, which could not see
either event the monthly job exists to catch. A landing page returns 200 long after
the `dataset_id` behind it is retired, and it says nothing at all about versions.

**`describe()` needs no credential.** It accepts no `username`, `password` or
`credentials_file` — `get()` and `subset()` accept all three — and reads no cached
credential file. The catalogue is public. `source-probe.yml` passed two Copernicus
secrets until C-c2 struck them; nothing had ever read them.

**`copernicusmarine` is imported inside the call, not at module scope.** The probe
job installs `[spatial]` as of C-c2, so the old reason (a bare install) is gone —
but the default test suite runs `-m 'not spatial'`, and `-m` deselects after
collection, so a module-scope import here would break collection of every test in
the repository.
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

    # Imported inside the function for the reason in the module docstring. A bare
    # `except Exception` would also catch it, but naming it is what lets `absent`
    # and `unreachable` be different answers.
    from copernicusmarine import DatasetNotFound

    try:
        catalogue = call(dataset_id=dataset_id, disable_progress_bar=True)
    except DatasetNotFound as error:
        return "absent", f"dataset absent from catalogue: {dataset_id} ({error})"
    except Exception as error:  # noqa: BLE001 - one dead source must not fail the job
        return "unreachable", f"unreachable: {error}"

    served = _served_versions(catalogue)
    if expected_version in served:
        return "ok", f"{dataset_id} serves version {expected_version}"
    return (
        "version_drift",
        f"{dataset_id} no longer serves the version the manifest records: "
        f"manifest says {expected_version}, catalogue serves {served}",
    )
