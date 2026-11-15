from basalt.calendar_utils import season_bounds, season_year


def test_punjab_season_wraps_new_year():
    start, end = season_bounds(2024, "06-01")
    assert season_year(start, "06-01") == 2024
    assert season_year(end, "06-01") == 2025
