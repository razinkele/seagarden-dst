"""The query year reaches the growth model, and an absent year excludes a species
rather than crashing the whole assessment (final-review commit 1).

No xarray here: these fakes stand in for a `GriddedForcing`-shaped `ForcingSource`,
so this file runs in the default selection.
"""

from __future__ import annotations

import pytest

from seagarden_dst import SiteContext, assess_site
from seagarden_dst.forcing import (
    DEFAULT_FORCING,
    PLACEHOLDER_YEAR,
    ForcingUnavailable,
    SiteReading,
)
from seagarden_dst.params import default_parameters


class _RecordingSource:
    """Delegates to the placeholder for numbers; records every year it is asked for."""

    def __init__(self) -> None:
        self.years: list[int] = []

    def reading_at(self, query):
        reading = DEFAULT_FORCING.reading_at(query)
        return SiteReading(
            conditions=reading.conditions,
            coverage=reading.coverage,
            year=query.year,
            aggregation=reading.aggregation,
            from_artifact=True,
        )

    def daily_forcing(self, site, window, year):
        self.years.append(year)
        return DEFAULT_FORCING.daily_forcing(site, window, year)


class _WrappingFailsSource(_RecordingSource):
    """Like `_RecordingSource`, but a wrapping window raises exactly the message an
    artifact reader raises when it lacks the following year."""

    def daily_forcing(self, site, window, year):
        start, end = window
        if end < start:
            raise ForcingUnavailable(
                f"artifact does not carry year {year + 1} (needed for a window "
                f"wrapping past {year})"
            )
        return super().daily_forcing(site, window, year)


def test_the_query_year_reaches_the_growth_model():
    """LT-lagoon is not contraindicated across the board (it is Ulva's own site), and
    the placeholder region carries no salinity floor issue for every species there."""
    fake = _RecordingSource()
    context = SiteContext.from_region("LT-lagoon", forcing=fake, year=2025)
    result = assess_site(context, forcing=fake, year=2025)

    assert result.ranked
    assert fake.years
    assert all(y == 2025 for y in fake.years)


def test_saccharinas_shipped_wrapping_window_never_reaches_daily_forcing():
    """`saccharina_latissima` has the shipped wrapping cultivation window [10, 6]
    (params/species/saccharina_latissima.yaml), but its `yield_model:
    salinity_indexed` means `growth.harvest_biomass` returns `f_salinity x
    max_yield_t_fw_ha` before ever calling `simulate`/`daily_forcing` - the ODE
    branch and its window are retained only for reference (see the species file's
    own notes). So a source that raises on a wrapping window is never actually
    asked for this species' window today, contraindication aside. Pinned here so
    that changes to `yield_model` or to this exclusion path are caught."""
    fake = _WrappingFailsSource()
    context = SiteContext.from_region("DK-belt", forcing=fake, year=2025)
    result = assess_site(context, forcing=fake, year=2025)

    assert "saccharina_latissima" not in result.excluded
    assert any(o.species_key == "saccharina_latissima" for o in result.ranked)


def test_a_wrapping_window_the_artifact_cannot_cover_excludes_only_that_species():
    """No shipped species integrates the ODE with a wrapping window (see the test
    above), so this manufactures one from `fucus_vesiculosus`'s own parameters -
    same group, same region behaviour, only the window and key changed - to
    exercise the exclusion path a future ODE species with a wrapping window (or
    Saccharina, were its `yield_model` ever switched back to 'ode') would hit."""
    params = default_parameters()
    wrapped = params.species["fucus_vesiculosus"].model_copy(
        update={"key": "fucus_wrapped", "cultivation_window": (10, 6)}
    )
    species = dict(params.species)
    species["fucus_wrapped"] = wrapped
    params = params.model_copy(update={"species": species})

    fake = _WrappingFailsSource()
    context = SiteContext.from_region("DK-belt", forcing=fake, year=2025)
    result = assess_site(
        context,
        forcing=fake,
        year=2025,
        params=params,
        species=["fucus_vesiculosus", "fucus_wrapped"],
    )

    assert any(o.species_key == "fucus_vesiculosus" for o in result.ranked)
    assert "fucus_wrapped" in result.excluded
    assert "wrapping" in result.excluded["fucus_wrapped"]
    assert all(o.species_key != "fucus_wrapped" for o in result.ranked)


def test_no_year_argument_still_passes_the_placeholder_year():
    fake = _RecordingSource()
    context = SiteContext.from_region("LT-lagoon", forcing=fake)
    assess_site(context, forcing=fake)

    assert fake.years
    assert all(y == PLACEHOLDER_YEAR for y in fake.years)


class _BrokenSource(_RecordingSource):
    """A source with a programming error: a plain ValueError, not a ForcingUnavailable."""

    def daily_forcing(self, site, window, year):
        raise ValueError("a bug in the source, not a window the artifact lacks")


def test_a_plain_value_error_from_a_source_is_not_hidden_as_an_exclusion():
    """Only `ForcingUnavailable` excludes. A bare ValueError is a defect (a broken
    species file, a bug in a source) and must fail loudly, not appear as a quietly
    excluded species in the results."""
    source = _BrokenSource()
    context = SiteContext.from_region("LT-lagoon", forcing=source)
    with pytest.raises(ValueError, match="a bug in the source"):
        assess_site(context, forcing=source, year=2025)


def test_forcing_unavailable_is_a_value_error_so_existing_reader_tests_hold():
    assert issubclass(ForcingUnavailable, ValueError)
