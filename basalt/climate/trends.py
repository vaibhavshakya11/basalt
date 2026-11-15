from collections.abc import Mapping

import numpy as np
import pandas as pd
import pymannkendall

from basalt.calendar_utils import calendar_windows, season_bounds
from basalt.contracts import ClimateTable, Crop, Rotation, Site

PERIOD = range(1991, 2026)
TREND_METRICS = {
    "heat_days": ("Heat days in sensitive crop stages", "days"),
    "main_season_rainfall": ("Main-season rainfall", "mm"),
    "annual_et0": ("Reference evapotranspiration", "mm"),
    "hottest_month_tmax": ("Average daytime maximum in the hottest month", "°C"),
}


def _heat_days(table: ClimateTable, windows) -> int:
    count = 0
    for window in windows:
        threshold = window.crop.tcrit_heat_c
        if threshold is not None:
            start = window.sow + pd.Timedelta(days=sum(window.stage_days[:2]))
            sensitive_days = min(15, window.stage_days[2])
            days = table.loc[start:start + pd.Timedelta(days=sensitive_days - 1), "tmax"]
            count += int((days >= threshold).sum())
    return count


def annual_series(
    table: ClimateTable, site: Site, rotation: Rotation, crops: Mapping[str, Crop],
) -> pd.DataFrame:
    """Aggregate only complete farming years within the requested trend period."""
    windows_by_year = {}
    for window in calendar_windows(rotation, crops, site.season_year_start, PERIOD):
        windows_by_year.setdefault(window.season, []).append(window)
    records = []
    for year in PERIOD:
        start, end = season_bounds(year, site.season_year_start)
        windows = windows_by_year.get(year, [])
        year_end = end - pd.Timedelta(days=1)
        observed_through = max([year_end, *(window.harvest for window in windows)])
        if start < table.index[0] or observed_through > table.index[-1]:
            continue
        season = table.loc[start:year_end]
        main_window = next(iter(windows), None)
        rain = table.loc[main_window.sow:main_window.harvest, "precip"].sum() if main_window else np.nan
        records.append({
            "season": year,
            "heat_days": _heat_days(table, windows),
            "main_season_rainfall": rain,
            "annual_et0": season["et0"].sum(),
            "hottest_month_tmax": season["tmax"].resample("MS").mean().max(),
        })
    return pd.DataFrame.from_records(records, columns=["season", *TREND_METRICS]).set_index("season")


def annual_trends(
    table: ClimateTable, site: Site, rotation: Rotation, crops: Mapping[str, Crop],
) -> list[dict]:
    """Report Hamed–Rao significance and Sen's slope per decade."""
    annual = annual_series(table, site, rotation, crops)
    if len(annual) < 4:
        return []
    trends = []
    for name, (metric, unit) in TREND_METRICS.items():
        series = annual[name].dropna()
        if len(series) < 4:
            continue
        values = series.to_numpy()
        if np.unique(values).size == 1:
            slope, p_value = 0.0, 1.0
        else:
            inference = pymannkendall.hamed_rao_modification_test(values)
            slope, p_value = float(inference.slope) * 10, float(inference.p)
        direction = "increase" if slope > 0 else "decrease"
        verdict = f"Statistically clear {direction} in NASA POWER data" if p_value < 0.05 and slope != 0 else "No clear change"
        trends.append({
            "metric": metric, "slope_per_decade": slope, "unit": unit,
            "p_value": p_value, "verdict": verdict, "n_seasons": len(series),
            "season_range": [int(series.index[0]), int(series.index[-1])],
        })
    return trends
