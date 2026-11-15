import numpy as np

from basalt.physics.waterbalance import rice_day, rice_refill, root_day


def test_daily_closure_under_dry_and_wet_weather():
    random = np.random.default_rng(56)
    dr = 25.
    for rain, potential in zip(random.gamma(0.7, 7, 731), random.uniform(1, 7, 731)):
        plant = root_day(dr, 100., 45., rain, potential, 78, dr if dr > 45 else 0., .6)
        assert abs(plant.residual) < .1
        assert 0 <= plant.dr <= 100.
        dr = plant.dr


def test_standing_water_and_rice_refill():
    pond = 0.
    for age in range(14):
        irrigation = rice_refill(pond, age, 0, 100 - age)
        day = rice_day(0., 60., 14., pond, 0., 5., irrigation, 8.)
        assert 0 < day.pond <= 100
        assert abs(day.residual) < .1
        pond = day.pond
    assert rice_refill(0., 22, 1, 70) == 0.
    assert rice_refill(0., 23, 2, 70) == 75.
    assert rice_refill(0., 97, 5, 13) == 0.
    assert rice_day(0., 60., 14., 75., 200., 4., 0., 8.).runoff == 113.


def test_full_punjab_replay_stops_wheat_irrigation_before_harvest():
    from basalt.climate.power import load_climate
    from basalt.config import DEMO
    from basalt.contracts import Site
    from basalt.knowledge.loader import load_crops, load_punjab_rotations, load_soils
    from basalt.physics.simulate import run_rotation

    site = Site("ludhiana", "Ludhiana", 30.8, 75.7, "calibrated", "loam", "soilgrids", True, "06-01")
    climate = load_climate(DEMO / "ludhiana" / "climate.parquet")
    rotation = load_punjab_rotations()["pb_rw"]
    run = run_rotation(site, climate, rotation, load_crops(), load_soils()["loam"], years=range(2001, 2003))
    for season in run.phases[0]:
        wheat = season.daily.irr_net[season.daily.crop_id == "wheat_pb"]
        assert np.any(wheat[:-14] > 0)
        assert np.all(wheat[-14:] == 0)
        assert season.result.wb_residual_max_mm < .1
