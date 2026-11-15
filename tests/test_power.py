from copy import deepcopy

import pandas as pd
import pytest

from basalt.climate.et0 import extraterrestrial_radiation, hargreaves
from basalt.climate.power import POWER_FIELDS, PowerError, fetch_power, parse_power
from basalt.climate.scenario import apply_scenario
from basalt.contracts import Scenario


@pytest.fixture
def payload():
    days = pd.date_range("2020-06-01", periods=8).strftime("%Y%m%d")
    samples = zip(POWER_FIELDS, (32, 19, 15, 54, 2, 24, 2, 98))
    return {
        "header": {
            "start": days[0], "end": days[-1], "fill_value": -999,
            "api": {"version": "fixture"}, "time_standard": "LST", "sources": ["fixture"],
        },
        "parameters": {code: {"units": units} for code, (_, units) in POWER_FIELDS.items()},
        "geometry": {"coordinates": [75.7, 30.8, 240]},
        "properties": {"parameter": {code: dict.fromkeys(days, value) for code, value in samples}},
    }


def test_short_gap_fills_and_long_radiation_gap_uses_hargreaves(payload):
    series = payload["properties"]["parameter"]
    for date in ("20200602", "20200603"):
        series["PRECTOTCORR"][date] = -999
    for date in ("20200604", "20200605", "20200606", "20200607"):
        series["ALLSKY_SFC_SW_DWN"][date] = -999
    table = parse_power(payload)
    assert table.at["2020-06-02", "precip"] == 2
    assert table["qc_filled"].tolist() == [False, True, True, True, True, True, True, False]
    day_of_year = pd.Timestamp("2020-06-05").dayofyear
    estimate = hargreaves(32, 19, extraterrestrial_radiation(30.8, day_of_year))
    assert table.at["2020-06-05", "et0"] == pytest.approx(estimate)


def test_unexpected_source_units_and_unsafe_gap_raise(payload):
    wrong_unit = deepcopy(payload)
    wrong_unit["parameters"]["ALLSKY_SFC_SW_DWN"]["units"] = "kW-hr/m^2/day"
    with pytest.raises(PowerError, match="Expected"):
        parse_power(wrong_unit)
    for day in ("20200602", "20200603", "20200604", "20200605"):
        payload["properties"]["parameter"]["PRECTOTCORR"][day] = -999
    with pytest.raises(PowerError, match="missing"):
        parse_power(payload)


def test_weather_cache_uses_half_degree_key_and_preserves_source_metadata(payload, tmp_path, monkeypatch):
    class PowerResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    sent = []

    def get(*args, **kwargs):
        sent.append(kwargs)
        return PowerResponse()

    monkeypatch.setattr("basalt.climate.power.requests.get", get)
    first = fetch_power(30.8, 75.7, "2020-06-01", "2020-06-08", cache_dir=tmp_path)
    second = fetch_power(30.9, 75.6, "2020-06-01", "2020-06-08", cache_dir=tmp_path)
    assert len(sent) == 1
    assert sent[0]["timeout"] == 60
    assert sent[0]["params"]["community"] == "AG"
    assert first.attrs == second.attrs
    pd.testing.assert_frame_equal(first, second, check_freq=False)


def test_scenario_changes_weather_then_recomputes_et0(payload):
    baseline = parse_power(payload)
    shifted = apply_scenario(baseline, Scenario(2, 0.9))
    assert shifted["tmax"].iat[0] == baseline["tmax"].iat[0] + 2
    assert shifted["tdew"].iat[0] == baseline["tdew"].iat[0] + 2
    assert shifted["precip"].iat[0] == pytest.approx(baseline["precip"].iat[0] * 0.9)
    assert shifted["et0"].iat[0] != pytest.approx(baseline["et0"].iat[0])
    pd.testing.assert_frame_equal(apply_scenario(shifted, Scenario()), baseline)
