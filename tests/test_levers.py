from dataclasses import replace

import numpy as np
import pandas as pd

from basalt.contracts import LocalCalendar, Site
from basalt.decision.levers import _suitable_days, make_current, propose_levers
from basalt.knowledge.loader import load_crops, load_soils


def test_warm_gap_has_enough_heat_for_mungbean_and_cowpea():
    days = pd.date_range("2001-07-01", periods=90)
    weather = pd.DataFrame({"tmax": 33., "tmin": 23.}, index=days)
    crops = load_crops()
    assert _suitable_days(weather, [(days[0], days[-1])], crops["mungbean"]) == [62]
    assert _suitable_days(weather, [(days[0], days[-1])], crops["cowpea"]) == [73]
    assert _suitable_days(weather.assign(tmin=2.), [(days[0], days[-1])], crops["mungbean"]) == []


def test_grown_legume_is_eligible_for_alternation_on_single_season_farm():
    site = Site("test", "Test plot", -10, 30, "global", "loam", "user", False, "01-01")
    dates = pd.date_range("2000-01-01", "2003-12-31")
    climate = pd.DataFrame({"et0": 4., "tmax": 32., "tmin": 20., "tdew": 15.,
                            "precip": np.where(dates.month <= 5, 6., 0.), "rh": 55., "ws2": 2.}, index=dates)
    maize, bean = (LocalCalendar(crop_id, "rf", 31, 150, 120, .1, "MapSPAM", code)
                   for crop_id, code in (("maize", "mai"), ("beans", "bea")))
    crops = load_crops()
    gaps = {"mungbean": replace(crops["mungbean"], min_window_days=1000)}
    current = make_current(["maize"], [maize])
    outcome = propose_levers(site, current, climate, crops, gaps, [maize, bean],
                             load_soils()["loam"], years=range(2001, 2004))
    assert any(rotation.lever == "take_turns" and rotation.cycle_years == 2 for rotation in outcome.rotations)
    assert any(row["lever"] == "fill_the_gap" and row["reason"] for row in outcome.rejected)
