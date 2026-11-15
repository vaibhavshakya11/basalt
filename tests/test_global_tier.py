from basalt.global_tier.ggcmi import calendar_slot, default_season_start, ggcmi_cell, local_calendars
from basalt.global_tier.grace import JPL_DATASET, regional_trend


def test_malawi_calendar_and_local_crop_screen():
    assert ggcmi_cell(-13.8, 33.45) == (-13.75, 33.25)
    calendars = local_calendars(-13.8, 33.45, False)
    by_crop = {calendar.crop_id: calendar for calendar in calendars}
    maize = by_crop["maize"]
    assert maize.harvested_frac > 0.01
    assert calendar_slot(maize).sow == "11-16"
    assert calendar_slot(maize).harvest == "05-29"
    assert default_season_start(maize) == "09-01"
    assert "groundnut" in by_crop
    assert "soybean" not in by_crop
    assert any(calendar.crop_id == "soybean" for calendar in local_calendars(-13.8, 33.45, False, grown_only=False))


def test_boundary_cells_wrap_longitude_without_clamping_to_land():
    assert ggcmi_cell(90, 180) == (89.75, -179.75)
    assert local_calendars(0, -150, False) == ()


def test_grace_demo_cells_use_the_public_jpl_series():
    ludhiana = regional_trend(30.80, 75.70)
    malawi = regional_trend(-13.80, 33.45)
    assert ludhiana["dataset"] == malawi["dataset"] == JPL_DATASET
    assert round(ludhiana["trend_cm_per_yr"], 2) == -3.94
    assert round(malawi["trend_cm_per_yr"], 2) == -0.51
