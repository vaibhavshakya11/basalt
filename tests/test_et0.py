import numpy as np
import pytest

from basalt.climate.et0 import example_18, extraterrestrial_radiation, hargreaves, penman_monteith


def test_fao56_example_18_in_brussels():
    terms = example_18()
    assert terms.et0 == pytest.approx(3.9, abs=0.1)
    assert terms.ra == pytest.approx(41.09, rel=0.02)
    assert terms.rso == pytest.approx(30.90, rel=0.02)
    assert terms.rn == pytest.approx(13.28, rel=0.02)


def test_hargreaves_fallback_keeps_radiation_in_equivalent_mm():
    terms = penman_monteith(
        tmax=[21.5, 21.5], tmin=[12.3, 12.3], ea=1.409,
        ws2=2.078, rs=[22.07, np.nan], ps=100.1,
        lat=50.8, elevation_m=100, day_of_year=[187, 187],
    )
    assert terms.et0[0] == pytest.approx(3.9, abs=0.1)
    assert terms.et0[1] == pytest.approx(3.97, abs=0.1)
    assert terms.et0[1] == pytest.approx(hargreaves(21.5, 12.3, extraterrestrial_radiation(50.8, 187)))
