from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np
import pandas as pd

from basalt.contracts import Crop, CropWindow, Rotation


def month_day(year: int, value: str) -> pd.Timestamp:
    month, day = (int(part) for part in value.split("-"))
    return pd.Timestamp(date(year, month, day))


def season_year(day: date | pd.Timestamp, start: str) -> int:
    return day.year - int(day.strftime("%m-%d") < start)


def season_bounds(year: int, start: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    return month_day(year, start), month_day(year + 1, start)


def doy_month_day(day: int) -> str:
    if not 1 <= day <= 366:
        raise ValueError(f"Invalid day of year: {day}")
    return (pd.Timestamp("2001-01-01") + pd.Timedelta(min(day, 365) - 1, unit="D")).strftime("%m-%d")


def stage_lengths(crop: Crop, total: int | None = None) -> tuple[int, int, int, int]:
    if total is None:
        if crop.stage_days is None:
            raise ValueError(f"{crop.crop_id} requires a harvest date")
        return crop.stage_days
    stages = np.asarray(crop.stage_fracs if crop.stage_fracs is not None else crop.stage_days, dtype=float)
    targets = stages * total / stages.sum()
    lengths = np.floor(targets).astype(int)
    order = np.argsort(-(targets - lengths), kind="stable")
    lengths[order[:total - lengths.sum()]] += 1
    return tuple(int(value) for value in lengths)


def calendar_windows(rotation: Rotation, crops: Mapping[str, Crop], start: str,
                     years: Sequence[int], phase: int = 0, shift_days: int = 0,
                     minimum_gap: int | None = None) -> tuple[CropWindow, ...]:
    if len(rotation.years) != rotation.cycle_years:
        raise ValueError("Year count must match rotation cycle")
    windows = []
    for year in years:
        for slot in rotation.years[(year - 2001 + phase) % rotation.cycle_years]:
            sow = month_day(year + (slot.sow < start), slot.sow)
            crop = crops[slot.crop_id]
            if slot.harvest is None:
                lengths = stage_lengths(crop)
                harvest = sow + pd.Timedelta(int(sum(lengths)) - 1, unit="D")
            else:
                harvest = month_day(sow.year + (slot.harvest < slot.sow), slot.harvest)
                lengths = stage_lengths(crop, (harvest - sow).days + 1)
            shift = pd.Timedelta(int(shift_days), unit="D")
            windows.append(CropWindow(crop, sow + shift, harvest + shift, year, lengths))
    windows.sort(key=lambda window: window.sow)
    if minimum_gap is not None:
        for previous, following in zip(windows, windows[1:]):
            if (following.sow - previous.harvest).days - 1 < minimum_gap:
                raise ValueError(f"{rotation.rotation_id}: fewer than {minimum_gap} bare days between {previous.crop.crop_id} and {following.crop.crop_id}")
    return tuple(windows)


def validate_rotation(rotation: Rotation, crops: Mapping[str, Crop], start: str) -> None:
    calendar_windows(rotation, crops, start, range(2000, 2004), minimum_gap=5)
