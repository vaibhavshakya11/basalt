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
