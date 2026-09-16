import pytest
from refresh_builders import manifest as build_manifest

from seagarden_dst.artifact.manifest import Manifest
from seagarden_dst.refresh.deposit import Depositor, record_doi

_DOI = "10.5281/zenodo.9999999"


class StubDepositor:
    """C§9: no Zenodo deposit is performed. The path is exercised, not the service."""

    def deposit(self, artifact, manifest):
        return _DOI


def test_the_stub_satisfies_the_depositor_protocol():
    assert isinstance(StubDepositor(), Depositor)


def test_recording_a_doi_flips_pending_layers_to_deposited():
    before = build_manifest()
    assert all(layer.archive.status == "pending" for layer in before.layers)
    after = record_doi(before, StubDepositor().deposit("forcing.nc", "manifest.json"))
    assert all(layer.archive.status == "deposited" for layer in after.layers)
    assert all(layer.archive.zenodo_doi == _DOI for layer in after.layers)


def test_the_flipped_manifest_still_validates():
    after = record_doi(build_manifest(), _DOI)
    Manifest.model_validate(after.model_dump())


def test_a_forbidden_layer_is_not_flipped():
    # C§6.1's last row: a layer marked forbidden is the mis-marking hazard, and a
    # deposit must not launder it into `deposited`.
    before = build_manifest()
    before.layers[0].archive.status = "forbidden"
    before.layers[0].archive.zenodo_doi = None
    after = record_doi(before, _DOI)
    assert after.layers[0].archive.status == "forbidden"
    assert after.layers[0].archive.zenodo_doi is None


def test_an_empty_doi_is_refused():
    with pytest.raises(ValueError, match="deposit returned no DOI"):
        record_doi(build_manifest(), "")


def test_a_whitespace_doi_is_refused():
    with pytest.raises(ValueError, match="deposit returned no DOI"):
        record_doi(build_manifest(), "   ")


def test_a_flip_that_would_break_the_archive_contract_is_caught():
    # The discriminating test for re-validation: `deposited` requires a zenodo_doi
    # (Archive._check_state_is_complete). If record_doi skipped the validators it
    # would happily emit a `deposited` layer with none.
    after = record_doi(build_manifest(), _DOI)
    after.layers[0].archive.zenodo_doi = None
    with pytest.raises(ValueError, match="requires a zenodo_doi"):
        Manifest.model_validate(after.model_dump())
