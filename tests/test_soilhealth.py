import pytest

from basalt.physics.soilhealth import soil_factors


def test_rice_wheat_has_no_legumes_or_rotation_of_families():
    assert soil_factors(90, .5, 0, True, ["Poaceae"], 25, 100) == pytest.approx({
        "living_cover": 1-90/365, "residue_kept": .5, "legume_months": 0.,
        "no_puddling": 0., "pest_cycle_break": 0., "erosive_rain_bare": .75,
    })
