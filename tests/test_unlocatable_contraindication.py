"""A site can be unlocatable and still be contraindicated.

§7 forces tier C outside every calibration domain; §3.2 forces tier D below a species'
salinity floor. §8.1 of the data-layer design resolves the overlap in favour of
contraindication. Tier C is the floor a result cannot rise above, not a ceiling that
stops it falling further.
"""

import dataclasses

from seagarden_dst.calibration import Tier
from seagarden_dst.forcing import PLACEHOLDER_SITES
from seagarden_dst.growth import contraindication
from seagarden_dst.params import default_parameters


def _sugar_kelp():
    # `default_parameters()` is the loader; `load_parameters(root)` is its rooted form.
    # There is no `load_params`.
    return default_parameters().species["saccharina_latissima"]


def test_a_below_floor_site_with_no_region_is_still_tier_d():
    """The canonical case: OLAMUR found outright cultivation failure at 5.5-6.5 psu
    while the salinity scaling returns a small positive yield. Losing the region must
    not lose the finding."""
    site = dataclasses.replace(
        PLACEHOLDER_SITES["LT-lagoon"], region=None, salinity_psu=2.0
    )
    calibration = contraindication(_sugar_kelp(), site)
    assert calibration is not None
    assert calibration.tier is Tier.D


def test_the_number_is_suppressed_in_favour_of_the_note():
    site = dataclasses.replace(
        PLACEHOLDER_SITES["LT-lagoon"], region=None, salinity_psu=2.0
    )
    calibration = contraindication(_sugar_kelp(), site)
    assert calibration.is_reportable is False
    assert calibration.caveat()


def test_an_above_floor_site_with_no_region_is_not_contraindicated():
    """The discriminating half: if this also returned tier D the first test would pass
    for a reason that has nothing to do with salinity."""
    site = dataclasses.replace(
        PLACEHOLDER_SITES["LT-coastal"], region=None, salinity_psu=25.0
    )
    assert contraindication(_sugar_kelp(), site) is None
