"""Cultivation windows that wrap the year boundary.

Sugar kelp is deployed in autumn and harvested the following early summer, so its
window runs October to June. The scaffold could not represent that: the parameter
validator rejected it outright, and `daily_forcing` built its day axis with
`arange(274, 180)`, which is empty - after which `growth.simulate` raised
`IndexError` on `days[0]`. The species file carried `[1, 6]` as a stand-in and said
in its own notes that this understates the yield.

The fix is that the day axis runs past 365 rather than being spliced at the year
boundary. The seasonal sinusoid has period 365.25, so day 370 and day 5 are the same
point in the season already; continuing the axis is all that is required, and it
keeps the forcing continuous across New Year.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from seagarden_dst import PLACEHOLDER_SITES, default_parameters
from seagarden_dst.forcing import daily_forcing, day_of_year
from seagarden_dst.growth import simulate
from seagarden_dst.params import SpeciesParams


@pytest.fixture(scope="module")
def params():
    return default_parameters()


@pytest.fixture(scope="module")
def site():
    return PLACEHOLDER_SITES["DK-belt"]


# --- the day axis -------------------------------------------------------------


def test_wrapping_window_produces_the_whole_span(site):
    """October to June is 271 days, not zero."""
    days, par, temp, din = daily_forcing(site, (10, 6))

    expected = (365 - day_of_year(10, 1)) + day_of_year(6, 28) + 1
    assert days.size == expected == 271
    assert par.size == temp.size == din.size == days.size


def test_the_day_axis_is_strictly_increasing_through_the_year_end(site):
    """Continuing past 365 - not splicing two segments - is what keeps it monotone.

    `growth.simulate` interpolates the growth rate with `np.interp`, which silently
    returns garbage on a non-monotone x. It must never see a day axis that jumps
    back to 1 at New Year.
    """
    days, *_ = daily_forcing(site, (10, 6))

    assert np.all(np.diff(days) > 0)
    assert days[0] == day_of_year(10, 1)
    assert days[-1] > 365  # the harvest is in the *following* calendar year


def test_forcing_is_continuous_across_new_year(site):
    """A spliced window would show a discontinuity at the join. This guards against
    a future 'fix' that concatenates two calendar segments instead."""
    wrapping, _, temp_wrap, _ = daily_forcing(site, (10, 6))
    _, _, temp_plain, _ = daily_forcing(site, (4, 10))

    biggest_plain_step = float(np.max(np.abs(np.diff(temp_plain))))
    biggest_wrap_step = float(np.max(np.abs(np.diff(temp_wrap))))

    assert biggest_wrap_step <= biggest_plain_step * 1.5


def test_the_non_wrapping_path_is_unchanged(site):
    """The fix must be a numerical no-op for every window that does not wrap.

    Fucus is anchored to a published reference range over April-October; if this
    moves, the fix was not minimal.
    """
    days, par, temp, din = daily_forcing(site, (4, 10))

    assert days[0] == day_of_year(4, 1) == 91
    assert days[-1] == day_of_year(10, 28) == 301
    assert days.size == 211
    assert np.all(days <= 365)


# --- the parameter validator --------------------------------------------------


def _species(window):
    kelp = default_parameters().species["saccharina_latissima"]
    return SpeciesParams(**{**kelp.model_dump(), "cultivation_window": window})


def test_a_wrapping_window_is_accepted():
    assert _species((10, 6)).cultivation_window == (10, 6)


def test_a_single_month_window_is_still_rejected():
    """(6, 6) is ambiguous once wrapping is legal - zero days, or a full year?"""
    with pytest.raises(ValidationError, match="at least two months"):
        _species((6, 6))


def test_months_outside_the_calendar_are_still_rejected():
    with pytest.raises(ValidationError, match="1-12"):
        _species((0, 6))
    with pytest.raises(ValidationError, match="1-12"):
        _species((10, 13))


# --- what it exposed ------------------------------------------------------


def test_the_autumn_deployment_window_ships(params):
    """The species file must carry the real window, not the January stand-in."""
    kelp = params.species["saccharina_latissima"]
    assert kelp.cultivation_window == (10, 6)


def test_the_trajectory_integrates_over_the_wrapping_window(params, site):
    """The end-to-end path that used to raise IndexError."""
    kelp = params.species["saccharina_latissima"]
    trajectory = simulate(kelp, site)

    assert trajectory.biomass.size == trajectory.days.size == 271
    assert np.all(np.isfinite(trajectory.biomass))
    assert trajectory.biomass[-1] > kelp.growth.b_initial


@pytest.mark.xfail(
    strict=True,
    reason=(
        "The placeholder DIN drawdown is indexed by position in the window rather "
        "than by calendar day. Unblocked by the section 6 climatologies; see the "
        "README's 'What is stubbed'. Fixing it moves the Tagalaht anchor, so the "
        "mu_max re-tune travels with it."
    ),
)
def test_nutrient_forcing_is_a_property_of_the_site_not_the_query(site):
    """Two species at one site must see the same nitrogen on the same day.

    They do not. On 1 April at DK-belt the site offers 3.15, 3.61 or 5.00 umol N/L
    according to which species' window was asked about, because `daily_forcing`
    spreads a fixed drawdown across however many days the window happens to contain.
    Found while fixing the wrapping window, which made the discrepancy large enough
    to change a published number - it is not caused by wrapping and predates it.

    Strict xfail on purpose: when the seasonal forcing lands this XPASSes and fails
    the suite, so the marker has to be removed deliberately rather than the finding
    quietly evaporating.
    """
    days_wrapping, _, _, din_wrapping = daily_forcing(site, (10, 6))
    days_plain, _, _, din_plain = daily_forcing(site, (1, 6))

    april = day_of_year(4, 1)
    under_wrapping = float(np.interp(april + 365, days_wrapping, din_wrapping))
    under_plain = float(np.interp(april, days_plain, din_plain))

    assert under_wrapping == pytest.approx(under_plain)
