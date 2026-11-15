import numpy as np
import pytest

from basalt.satellite.ornl import ET_BAND, ET_PRODUCT, ET_QC, NDVI_BAND, NDVI_PRODUCT, NDVI_QC, _read_subset


def subset(values, quality, value_band, quality_band):
    return {
        "nrows": 5, "ncols": 5,
        "subset": [
            {"band": band, "calendar_date": "2020-06-01", "data": pixels.ravel().tolist()}
            for band, pixels in ((value_band, values), (quality_band, quality))
        ],
    }


def test_ndvi_uses_center_nine_pixels_and_reliability_filter():
    values = np.full((5, 5), 9000)
    values[1:4, 1:4] = [[5000, 6000, -3000], [2000, 5500, 6000], [4000, 5000, 6000]]
    reliability = np.zeros((5, 5), dtype=int)
    reliability[2, 1] = 3
    reliability[1, 2] = 1
    result = _read_subset(subset(values, reliability, NDVI_BAND, NDVI_QC), NDVI_PRODUCT)
    median, n = result["2020-06-01"]
    assert median == pytest.approx(0.55)
    assert n == 7


def test_et_excludes_land_mask_codes_and_scales_to_mm():
    values = np.full((5, 5), 999)
    values[1:4, 1:4] = [[57, 32765, 59], [57, 47, 57], [57, 999, 57]]
    quality = np.zeros((5, 5), dtype=int)
    quality[3, 2] = 7 << 5
    result = _read_subset(subset(values, quality, ET_BAND, ET_QC), ET_PRODUCT)
    et_mm, n = result["2020-06-01"]
    assert et_mm == pytest.approx(5.7)
    assert n == 7
