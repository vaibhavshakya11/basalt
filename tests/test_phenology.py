import numpy as np
import pandas as pd

from basalt.satellite.phenology import detect_phenology


def test_two_modis_greenness_cycles_recovered_to_eight_days():
    start = pd.Timestamp("2020-01-01")
    dates = pd.date_range("2019-10-24", "2021-02-15", freq="16D")
    offsets = (dates - start).days.to_numpy()
    width = 29
    first, second = (87, 267)
    values = 0.17 + 0.58 * np.exp(-0.5 * ((offsets - first) / width) ** 2)
    values += 0.53 * np.exp(-0.5 * ((offsets - second) / width) ** 2)
    values[0] = np.nan
    ndvi = pd.DataFrame({"ndvi": values}, index=dates)
    report = detect_phenology(ndvi, "01-01")
    assert report["n_seasons"] == 2
    assert report["rejected_composite_share"] == 1 / len(values)
    margin = width * np.sqrt(-2 * np.log(0.2))
    for cycle, expected_peak in zip(report["seasons"][2020], (first, second), strict=True):
        for key, expected in (("sow_est", expected_peak - margin), ("peak", expected_peak), ("harvest_est", expected_peak + margin)):
            recovered = (pd.Timestamp(cycle[key]) - start).days
            assert abs(recovered - expected) <= 8
    assert 0 < report["bare_days"][2020] < 366


def test_agricultural_year_follows_the_start_of_the_greenness_cycle():
    dates = pd.date_range("2020-07-01", "2021-06-01", freq="16D")
    offsets = (dates - pd.Timestamp("2021-01-15")).days.to_numpy()
    ndvi = pd.DataFrame({"ndvi": 0.16 + 0.64 * np.exp(-0.5 * (offsets / 36) ** 2)}, index=dates)
    report = detect_phenology(ndvi, "09-01")
    assert report["n_seasons"] == 1
    assert list(report["seasons"]) == [2020]
    cycle = report["seasons"][2020][0]
    assert cycle["sow_est"].startswith("2020-")
    assert cycle["harvest_est"].startswith("2021-")


def test_low_greenness_does_not_create_a_crop_season():
    dates = pd.date_range("2020-01-01", periods=24, freq="16D")
    ndvi = pd.DataFrame({"ndvi": 0.25}, index=dates)
    report = detect_phenology(ndvi, "01-01")
    assert report["n_seasons"] == 0
    assert report["bare_days"] == {2020: 366, 2021: 3}
