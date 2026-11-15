import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter

from basalt.calendar_utils import season_year

SMOOTHING_DAYS = 81
MIN_PEAK_SEPARATION_DAYS = 60
MIN_NDVI_PEAK = 0.45
MIN_PROMINENCE = 0.15
GREENUP_FRAC = 0.20


def _upper_envelope(values: np.ndarray) -> np.ndarray:
    window = min(SMOOTHING_DAYS, len(values) if len(values) % 2 else len(values) - 1)
    if window < 5:
        return values
    upper = values
    for _ in range(3):
        smoothed = savgol_filter(upper, window_length=window, polyorder=2)
        upper = np.maximum(upper, smoothed)
    return smoothed


def _troughs(curve: np.ndarray, peaks: np.ndarray) -> list[int]:
    boundaries = np.r_[0, peaks, len(curve) - 1]
    return [
        int(start + np.argmin(curve[start:stop + 1]))
        for start, stop in zip(boundaries, boundaries[1:])
    ]


def _growing_bounds(curve: np.ndarray, peak: int, left: int, right: int) -> tuple[int, int]:
    left_limit = curve[left] + GREENUP_FRAC * (curve[peak] - curve[left])
    right_limit = curve[right] + GREENUP_FRAC * (curve[peak] - curve[right])
    left_cross = np.flatnonzero(curve[left:peak] < left_limit)
    right_cross = np.flatnonzero(curve[peak:right + 1] < right_limit)
    start = left + int(left_cross[-1]) + 1 if left_cross.size else left
    harvest = peak + int(right_cross[0]) - 1 if right_cross.size else right
    return start, harvest


def detect_phenology(ndvi: pd.DataFrame, season_start: str) -> dict:
    """Identify MODIS greenness cycles and bare days by agricultural year."""
    observed = ndvi["ndvi"].sort_index()
    values = observed.dropna()
    rejected = float(observed.isna().mean()) if len(observed) else 1.0
    report = {"seasons": {}, "n_seasons": 0, "bare_days": {}, "rejected_composite_share": rejected}
    if len(values) < 3:
        return report
    dates = pd.date_range(values.index.min(), values.index.max(), name="date")
    daily = values.reindex(dates).interpolate(method="time")
    curve = _upper_envelope(daily.to_numpy())
    peaks, _ = find_peaks(curve, height=MIN_NDVI_PEAK, prominence=MIN_PROMINENCE, distance=MIN_PEAK_SEPARATION_DAYS)
    troughs = _troughs(curve, peaks)
    cropped = np.zeros(len(curve), dtype=bool)
    for peak, left, right in zip(peaks, troughs, troughs[1:]):
        if (left == 0 and curve[left] >= MIN_NDVI_PEAK) or (right == len(curve) - 1 and curve[right] >= MIN_NDVI_PEAK):
            continue
        start, end = _growing_bounds(curve, peak, left, right)
        year = season_year(dates[start], season_start)
        report["seasons"].setdefault(year, []).append({
            "sow_est": dates[start].date().isoformat(),
            "peak": dates[peak].date().isoformat(),
            "harvest_est": dates[end].date().isoformat(),
        })
        report["n_seasons"] += 1
        cropped[start:end + 1] = True
    farming_years = np.fromiter((season_year(day, season_start) for day in dates), dtype=int, count=len(dates))
    report["bare_days"] = {
        int(year): int(np.count_nonzero((farming_years == year) & ~cropped)) for year in np.unique(farming_years)
    }
    return report
