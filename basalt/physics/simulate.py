from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from itertools import pairwise

import numpy as np
import pandas as pd

from basalt.calendar_utils import calendar_windows, season_bounds
from basalt.config import YEARS
from basalt.contracts import (
    ClimateTable, Constraints, Crop, CropWindow, DailyState, ModelParameters,
    Rotation, RotationRun, SeasonResult, SeasonRun, Site, Soil,
)
from basalt.physics.risks import burn_pressure, crop_events, erosion
from basalt.physics.soilhealth import FACTORS, score, soil_factors
from basalt.physics.waterbalance import CURVE_NUMBERS, readily_available, rice_day, rice_refill, root_day


@dataclass
class FieldDays:
    crop: np.ndarray
    stage: np.ndarray
    kc: np.ndarray
    root: np.ndarray
    depletion_fraction: np.ndarray
    days_left: np.ndarray
    age: np.ndarray
    rice: np.ndarray
    puddling: np.ndarray
    heat: np.ndarray
    frost: np.ndarray
    residue_cover: np.ndarray


def _stage_curve(window: CropWindow, rhmin: np.ndarray, wind: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    crop = window.crop
    initial, develop, middle, late = window.stage_days
    stage = np.repeat(["ini", "dev", "mid", "late"], window.stage_days)
    adjustments = (0.04 * (wind - 2) - 0.004 * (rhmin - 45)) * (crop.height_m / 3)**.3
    mid_start = initial + develop
    mid_kc = crop.kc_mid + (adjustments[mid_start:mid_start + middle].mean() if middle else 0.)
    end_kc = crop.kc_end
    if end_kc >= .45 and late:
        end_kc += adjustments[-late:].mean()
    coefficients = np.r_[np.full(initial, crop.kc_ini),
                         np.linspace(crop.kc_ini, mid_kc, develop + 1)[1:],
                         np.full(middle, mid_kc), np.linspace(mid_kc, end_kc, late + 1)[1:]]
    root = np.r_[np.linspace(crop.zr_min_m, crop.zr_max_m, max(1, mid_start))[:mid_start],
                 np.full(middle + late, crop.zr_max_m)]
    return stage, np.maximum(0., coefficients), root


def _schedule(dates: pd.DatetimeIndex, climate: ClimateTable, site: Site,
              windows: tuple[CropWindow, ...], constraints: Constraints,
              parameters: ModelParameters) -> tuple[FieldDays, dict[int, float]]:
    size = len(dates)
    zeros = lambda: np.zeros(size)
    days = FieldDays(np.full(size, "bare", dtype="U24"), np.full(size, "bare", dtype="U4"),
                     zeros(), np.full(size, .15), np.full(size, .55), np.full(size, -1),
                     np.full(size, -1), *[np.zeros(size, dtype=bool) for _ in range(5)])
    tmax, tmin, tdew, rh, wind = (climate[column].to_numpy() for column in ("tmax", "tmin", "tdew", "rh", "ws2"))
    sat = lambda temp: np.exp(17.27 * temp / (temp + 237.3))
    rhmin = np.clip(np.where(np.isfinite(tdew), 100 * sat(tdew) / sat(tmax), rh), 20, 80)
    wind = np.clip(wind, 1, 6)
    previous_burn = {}
    for previous, following in pairwise(windows):
        gap = (following.sow - previous.harvest).days
        pressure = burn_pressure(previous.crop.residue, gap, constraints.has_residue_machinery,
                                 parameters.burn_days_shift)
        previous_burn[previous.season] = max(previous_burn.get(previous.season, 0.), pressure)
        if pressure < .5 and previous.crop.residue in {"medium", "high"}:
            start = max(0, (previous.harvest - dates[0]).days + 1)
            stop = max(0, (following.sow - dates[0]).days)
            days.residue_cover[start:stop] = True
    for window in windows:
        start = (window.sow - dates[0]).days
        stop = start + sum(window.stage_days)
        rice = window.crop.ponded and site.irrigated
        if rice and start > 0:
            days.puddling[max(0, start - 7):start] = True
        lo, hi = max(0, start), min(size, stop)
        if hi <= lo:
            continue
        crop_slice = slice(lo, hi)
        start_trim, stop_trim = lo - start, hi - start
        pad = ((start_trim, stop-hi),)
        stage, kc, root = _stage_curve(window, np.pad(rhmin[crop_slice], pad, mode="edge"),
                                       np.pad(wind[crop_slice], pad, mode="edge"))
        events = crop_events(window.crop, stage, np.pad(tmax[crop_slice], pad, mode="edge"),
                             np.pad(tmin[crop_slice], pad, mode="edge"))
        crop_days = slice(start_trim, stop_trim)
        days.crop[crop_slice] = window.crop.crop_id
        days.residue_cover[crop_slice] = False
        days.stage[crop_slice], days.kc[crop_slice], days.root[crop_slice] = (arr[crop_days] for arr in (stage, kc, root))
        days.heat[crop_slice], days.frost[crop_slice] = (arr[crop_days] for arr in events)
        days.depletion_fraction[crop_slice] = window.crop.p
        days.days_left[crop_slice] = np.arange(stop-hi + hi-lo-1, stop-hi-1, -1)
        days.age[crop_slice] = np.arange(start_trim, stop_trim)
        days.rice[crop_slice] = rice
    return days, previous_burn


def _water(days: FieldDays, rain: np.ndarray, ref_et: np.ndarray, soil: Soil,
           site: Site, parameters: ModelParameters) -> tuple[DailyState, np.ndarray, np.ndarray]:
    taw = 1000 * (soil.theta_fc - soil.theta_wp) * days.root
    soil_arrays = np.zeros((10, len(taw)))
    kc, etc, actual_et, ks, drs, runoff, net, gross, drainage, ponds = soil_arrays
    cn_crop, cn_bare = CURVE_NUMBERS[soil.hydrologic_group]
    percolation = parameters.rice_percolation if parameters.rice_percolation is not None else soil.rice_percolation
    dr = pond = 0.
    empty_days = 0
    was_rice = False
    pending_refill = False
    last_wet = -4
    residuals = np.zeros(len(taw))
    events = np.zeros(len(taw), dtype=bool)
    for i, total_water in enumerate(taw):
        if i and total_water < taw[i - 1]:
            dr *= total_water / taw[i - 1]
        planted = days.stage[i] != "bare"
        puddling = days.puddling[i] and not planted
        rice = days.rice[i]
        if rice and not was_rice:
            empty_days = 0
        irrigable = site.irrigated and planted and days.days_left[i] >= 14
        if rice:
            irrigation = rice_refill(pond, days.age[i], empty_days, days.days_left[i])
        elif puddling:
            irrigation = parameters.puddling_mm / 7
        else:
            same_crop = i > 0 and days.age[i] == days.age[i-1] + 1
            irrigation = dr if irrigable and same_crop and pending_refill else 0.
        if rain[i] >= 5 or irrigation >= 5:
            last_wet = i
        kc[i] = days.kc[i] if planted else (.25 if i - last_wet < 3 else .10)
        etc[i] = kc[i] * ref_et[i]
        raw = readily_available(total_water, days.depletion_fraction[i], etc[i])
        if rice or puddling:
            water = rice_day(dr, total_water, raw, pond, rain[i], etc[i], irrigation, percolation)
        else:
            water = root_day(dr, total_water, raw, rain[i], etc[i], cn_crop if planted else cn_bare,
                             irrigation, parameters.irrigation_efficiency, pond)
        dr, pond = water.dr, water.pond
        actual_et[i], ks[i], drs[i], runoff[i] = water.et, water.ks, dr, water.runoff
        net[i], gross[i], drainage[i], ponds[i] = water.net, water.gross, water.drainage, pond
        residuals[i] = abs(water.residual)
        pending_refill = planted and not rice and dr > raw
        empty_days = empty_days + 1 if pond == 0 else 0
        was_rice = rice
        events[i] = irrigation > 0 and (not puddling or not days.puddling[i - 1] or i == 0)
    dry = (ks < .5) & (days.stage == "mid") & (not site.irrigated)
    water = DailyState(days.crop, days.stage, kc, etc, actual_et, ks, drs, taw, rain, runoff,
                       net, gross, drainage, ponds, days.heat, days.frost, np.zeros(len(rain), dtype=bool), dry)
    return water, residuals, events


def _crop_risk(windows: tuple[CropWindow, ...], daily: DailyState, first: pd.Timestamp) -> dict[int, list]:
    risks = {}
    for window in windows:
        lo, hi = (window.sow - first).days, (window.harvest - first).days + 1
        if lo < 0 or hi > len(daily.stage):
            continue
        crop_days = slice(lo, hi)
        heat = int(daily.heat_event[crop_days].sum())
        frost = int(daily.frost_event[crop_days].sum())
        mid = int((daily.stage[crop_days] == "mid").sum())
        dry = float(daily.dry_stress_event[crop_days].sum() / mid) if mid else 0.
        risks.setdefault(window.season, []).append((heat, frost, dry))
    return risks


def _run_phase(site: Site, climate: ClimateTable, rotation: Rotation, crops: Mapping[str, Crop],
               soil: Soil, constraints: Constraints, parameters: ModelParameters,
               years: Sequence[int], phase: int, shift_days: int) -> tuple[SeasonRun, ...]:
    start, _ = season_bounds(years[0] - 1, site.season_year_start)
    _, end = season_bounds(years[-1], site.season_year_start)
    windows = calendar_windows(rotation, crops, site.season_year_start, range(years[0] - 2, years[-1] + 2),
                               phase, shift_days, minimum_gap=0)
    latest = max((w.harvest for w in windows if w.season <= years[-1]), default=end)
    stop = min(max(end - pd.Timedelta(1, unit="D"), latest), climate.index[-1])
    dates = pd.date_range(start, stop)
    weather = climate.reindex(dates)
    for column in ("et0", "precip", "tmax", "tmin", "ws2"):
        if not np.isfinite(weather[column]).all():
            raise ValueError(f"Missing {column} in the replay period")
    if dates[-1] < end - pd.Timedelta(1, unit="D"):
        raise ValueError("Climate does not cover the complete replay period")
    days, burn = _schedule(dates, weather, site, windows, constraints, parameters)
    daily, residuals, events = _water(days, weather.precip.to_numpy(), weather.et0.to_numpy(), soil, site, parameters)
    erosivity, erosive_bare = erosion(daily.rain, days.stage, days.residue_cover)
    daily = replace(daily, erosive_bare_event=erosive_bare)
    families = {crops[slot.crop_id].family for group in rotation.years for slot in group}
    legumes = np.isin(days.crop, [crop_id for crop_id, crop in crops.items() if crop.family == "Fabaceae"])
    crop_risk = _crop_risk(windows, daily, dates[0])
    runs = []
    for year in years:
        year_start, year_end = season_bounds(year, site.season_year_start)
        idx = slice((year_start - dates[0]).days, (year_end - dates[0]).days)
        heat, frost, dry = zip(*crop_risk.get(year, [(0, 0, 0.)]))
        heat_hit, frost_hit, dry_hit = sum(x >= 3 for x in heat), sum(x >= 1 for x in frost), sum(x >= .3 for x in dry)
        applications = int(events[idx].sum())
        limit = constraints.irrigations_per_year_max
        bare = int((days.stage[idx] == "bare").sum())
        erosion_total = float(erosivity[idx].sum())
        pressure = burn.get(year, 0.)
        factors = soil_factors(bare, pressure, int(legumes[idx].sum()),
                               bool(days.rice[idx].any() or days.puddling[idx].any()), families, erosion_total, 0.)
        totals = [float(column[idx].sum()) for column in
                  (daily.etc_adj, daily.irr_net, daily.irr_gross, daily.rain, daily.runoff, daily.deep_perc)]
        result = SeasonResult(year, *totals[:3], applications, *totals[3:], sum(heat), heat_hit, sum(frost), frost_hit,
                              max(dry), dry_hit, heat_hit + frost_hit + dry_hit, bare, erosion_total, pressure, factors,
                              score(factors, parameters.soil_weights), float(residuals[idx].max()),
                              bool(limit is not None and applications > limit))
        runs.append(SeasonRun(year, dates[idx], DailyState(*(getattr(daily, attr.name)[idx] for attr in fields(DailyState))), result))
    return tuple(runs)


def _mean_result(phase_results: Sequence[SeasonResult]) -> SeasonResult:
    first = phase_results[0]
    if len(phase_results) == 1:
        return first
    values = {}
    for field in fields(SeasonResult):
        key = field.name
        if key in {"season", "soil_factors"}:
            continue
        entries = [getattr(result, key) for result in phase_results]
        if key == "irr_exceeds_limit":
            values[key] = any(entries)
        elif key == "wb_residual_max_mm":
            values[key] = max(entries)
        else:
            values[key] = float(np.mean(entries))
    values["soil_factors"] = {key: float(np.mean([r.soil_factors[key] for r in phase_results])) for key in FACTORS}
    return replace(first, **values)


def run_rotation(site: Site, climate: ClimateTable, rotation: Rotation, crops: Mapping[str, Crop],
                 soil: Soil, constraints: Constraints = Constraints(), *, years: Sequence[int] = YEARS,
                 parameters: ModelParameters = ModelParameters(), shift_days: int = 0,
                 erosion_ref: float | None = None) -> RotationRun:
    """Run each rotation phase continuously, including the preceding spin-up year."""
    if tuple(years) != tuple(range(years[0], years[-1]+1)):
        raise ValueError("Season years must be contiguous and in ascending order")
    phases = tuple(_run_phase(site, climate, rotation, crops, soil, constraints, parameters, years, phase, shift_days)
                   for phase in range(rotation.cycle_years))
    rotation_run = RotationRun(rotation, tuple(_mean_result([season.result for season in same_year])
                                               for same_year in zip(*phases)), phases)
    return apply_erosion_reference(rotation_run, erosion_ref, parameters.soil_weights)


def apply_erosion_reference(run: RotationRun, reference: float | None = None,
                            weights: tuple[float, ...] = ModelParameters().soil_weights) -> RotationRun:
    if reference is None:
        reference = float(np.percentile([season.erosion_index for season in run.seasons], 95))
    phases = []
    for phase in run.phases:
        scenarios = []
        for season in phase:
            result = season.result
            loss = min(1., result.erosion_index / reference) if reference > 0 else float(result.erosion_index > 0)
            factors = {**result.soil_factors, "erosive_rain_bare": 1 - loss}
            scenarios.append(replace(season, result=replace(result, soil_factors=factors, soil_score=score(factors, weights))))
        phases.append(tuple(scenarios))
    means = tuple(_mean_result([season.result for season in same_year]) for same_year in zip(*phases))
    return RotationRun(run.rotation, means, tuple(phases))
