from collections.abc import Mapping
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.stats import spearmanr

from basalt.calendar_utils import calendar_windows, validate_rotation
from basalt.climate.et0 import example_18
from basalt.config import DATA, YEARS
from basalt.contracts import Crop, CropSlot, RotationRun, Site, ValidationResult
from basalt.decision.replay import compare_runs, replay_runs
from basalt.global_tier.ggcmi import calendar_slot, ggcmi_cell, local_calendars
from basalt.knowledge.loader import load_soils

FIRMS = DATA / "firms" / "ludhiana_pentads.parquet"
SMAP = DATA / "smap" / "malawi_smap_l4.parquet"
CHECKS = {
    "V1": ("FAO-56 Example 18", "1998", "6 July", "Reference water use", "mm/day", "3.9 ± 0.1 mm/day"),
    "V2": ("GGCMI Phase 3 and PAU crop calendars", "1.01 / 2026", "2001 to 2024", "Global and calibrated arrow agreement", "%", "Pass at 75% or more. Caveat at 50% to under 75%."),
    "V3": ("MODIS MOD13Q1 via ORNL DAAC", "061", "2001 to 2024", "Median calendar date difference", "days", "Pass at 14 days or less. Caveat at 28 days or less."),
    "V4": ("NASA POWER and FAO-56", "Daily AG / Eq. 85", "2001 to 2024", "Largest daily water balance difference", "mm/day", "Under 0.1 mm/day."),
    "V5": ("NASA FIRMS VIIRS S-NPP", "375 m", "2012 to 2024", "Fires in the post-rice window", "%", "Consistent at 50% or more of September to December fires."),
    "V6": ("NASA POWER and published Punjab ranges", "Daily AG", "2001 to 2024", "Rice reference water and wheat irrigation", "", "430 to 510 mm and 3 to 6 applications."),
    "V7": ("NASA SMAP root-zone wetness", "SPL4SMGP.008", "2015 to 2024", "Soil wetness agreement", "Spearman r", "Pass at 0.5 or above. Caveat at 0.3 or above."),
    "V8": ("MODIS MOD16A2GF via ORNL DAAC", "061", "2001 to 2024", "Median seasonal water use bias", "%", "Always shown with a caveat about satellite water use."),
}


def _result(check: str, site: Site, status: str, note: str, *, n: int = 0, value=None) -> ValidationResult:
    dataset, version, period, metric, unit, rule = CHECKS[check]
    return ValidationResult(check_id=check, site=site.site_id, dataset=dataset, version=version, period=period,
                            n=n, metric=metric, value=value, unit=unit, pass_rule=rule,
                            status=status, note=note, figure_path=None)


def _compare_tiers(site, climate, runs, crops):
    if site.site_id != "ludhiana":
        return _result("V2", site, "not_run", "The calibrated comparison applies to Ludhiana.")
    if not site.irrigated:
        return _result("V2", site, "not_run", "The Ludhiana comparison uses irrigated crop calendars.")
    available = {row.crop_id: row for row in local_calendars(site.lat, site.lon, True, grown_only=False)
                 if row.crop_code != "ri2"}
    pairing = {"rice_pb": "rice", "wheat_pb": "wheat_winter", "maize_pb": "maize"}
    if not set(pairing.values()) <= available.keys():
        return _result("V2", site, "not_run", "The irrigated GGCMI calendars do not cover all the Punjab crops at this pin.")
    global_site = replace(site, tier="global", ggcmi_cell=ggcmi_cell(site.lat, site.lon))
    global_rotations = []
    incompatible = []
    for run in runs.values():
        converted = []
        for group in run.rotation.years:
            slots = []
            for slot in group:
                if slot.crop_id == "moong_pb":
                    month, day = map(int, slot.sow.split("-"))
                    sow = pd.Timestamp(2001, month, day)
                    harvest = (sow + timedelta(days=sum(crops["moong_pb"].stage_days) - 1)).strftime("%m-%d")
                    slots.append(CropSlot("mungbean", slot.sow, harvest))
                else:
                    slots.append(calendar_slot(available[pairing[slot.crop_id]]))
            converted.append(tuple(slots))
        rotation = replace(run.rotation, years=tuple(converted))
        try:
            validate_rotation(rotation, crops, global_site.season_year_start)
        except ValueError:
            incompatible.append(run.rotation.name)
        global_rotations.append(rotation)
    if incompatible:
        rice = calendar_slot(available["rice"])
        wheat = calendar_slot(available["wheat_winter"])
        rice_length = available["rice"].season_len
        wheat_length = available["wheat_winter"].season_len
        moong_length = sum(crops["moong_pb"].stage_days)
        note = (f"GGCMI rice spans {rice.sow} to {rice.harvest}. Winter wheat spans "
                f"{wheat.sow} to {wheat.harvest}. These dates overlap here. Rice, wheat and the "
                f"Punjab moong window require {rice_length + wheat_length + moong_length} crop days before any gaps.")
        return _result("V2", site, "not_run", note)
    global_runs = replay_runs(global_site, climate, global_rotations, crops, load_soils()[site.soil_class])
    calibrated, global_arrows = compare_runs(runs, site.irrigated), compare_runs(global_runs, site.irrigated)
    pairs = [(arrow, global_arrows[key][axis])
             for key, row in calibrated.items() for axis, arrow in row.items()]
    percent = 100 * sum(left == right for left, right in pairs) / len(pairs)
    metrics = {}
    for field, label in (("et_mm", "ET difference (mm)"), ("soil_score", "Soil score difference")):
        metrics[label] = float(np.median([abs(np.median([getattr(year, field) for year in run.seasons]) -
                                                    np.median([getattr(year, field) for year in global_runs[key].seasons]))
                                         for key, run in runs.items()]))
    status = "pass" if percent >= 75 else "caveat" if percent >= 50 else "fail"
    return _result("V2", site, status, "Compared each arrow using the same soil and weather.",
                   n=len(pairs), value={"Arrow agreement (%)": percent, **metrics})


def _calendar_validation(site: Site, rotation, crops, phenology):
    if phenology is None or not phenology["seasons"]:
        return _result("V3", site, "not_run", "There are no usable satellite growing periods for comparison.")
    windows = calendar_windows(rotation, crops, site.season_year_start, YEARS)
    by_year = {}
    for window in windows:
        by_year.setdefault(window.season, []).append(window)
    mismatches = []
    matched = 0
    for season, found in phenology["seasons"].items():
        predicted = by_year.get(int(season), [])
        if not predicted or not found:
            continue
        deltas = np.array([[(abs((crop.sow - pd.Timestamp(peak["sow_est"])).days),
                            abs((crop.harvest - pd.Timestamp(peak["harvest_est"])).days))
                           for peak in found] for crop in predicted])
        left, right = linear_sum_assignment(deltas.sum(axis=2))
        for i, j in zip(left, right):
            mismatches.extend(deltas[i, j])
            matched += 1
    if not mismatches:
        return _result("V3", site, "not_run", "The satellite dates could not be paired with the current calendar.")
    typical = float(np.median(mismatches))
    status = "pass" if typical <= 14 else "caveat" if typical <= 28 else "fail"
    rejected = 100 * phenology["rejected_composite_share"]
    return _result("V3", site, status, f"{matched} crop periods paired. {rejected:.1f}% of composites rejected by quality screening.",
                   n=len(mismatches), value=typical)


def _fires(site: Site, current, crops):
    if site.site_id != "ludhiana":
        return _result("V5", site, "not_run", "The fire overlap check is specific to the Ludhiana demo.")
    if not FIRMS.is_file():
        return _result("V5", site, "not_run", "The annual NASA FIRMS fire data have not been loaded.")
    windows = calendar_windows(current.rotation, crops, site.season_year_start, range(2012, 2025))
    ranges = [(a.harvest - timedelta(days=5), b.sow + timedelta(days=5)) for a, b in zip(windows, windows[1:])
              if a.crop.crop_id == "rice_pb" and b.crop.crop_id == "wheat_pb"]
    if not ranges:
        return _result("V5", site, "not_run", "The selected calendar has no rice-to-wheat transition.")
    match = 0
    fires = pd.read_parquet(FIRMS)
    total = int(fires.fires.sum())
    for row in fires.itertuples():
        for offset, count in enumerate(row.daily_counts):
            day = pd.Timestamp(row.start) + timedelta(days=offset)
            if any(start <= day <= end for start, end in ranges):
                match += int(count)
    if total == 0:
        return _result("V5", site, "not_run", "No qualifying fires are available to calculate a share.")
    share = 100 * match / total
    text = "Fire timing is consistent with the post-rice window." if share >= 50 else "Most fires fell outside the post-rice window."
    return _result("V5", site, "pass" if share >= 50 else "caveat", f"{text} Fire detections do not identify what burned.",
                   n=total, value=share)


def _sanity(site: Site, climate, current):
    if site.site_id != "ludhiana" or current.rotation.rotation_id != "pb_rw" or not site.irrigated:
        return _result("V6", site, "not_run", "The published comparison applies to irrigated rice and wheat at Ludhiana.")
    reference, wheat = [], []
    for season in current.phases[0]:
        reference.append(float(climate.loc[season.dates, "et0"].to_numpy()[season.daily.crop_id == "rice_pb"].sum()))
        wheat.append(int(((season.daily.crop_id == "wheat_pb") & (season.daily.irr_net > 0)).sum()))
    median_et, median_irr = float(np.median(reference)), float(np.median(wheat))
    status = "pass" if 430 <= median_et <= 510 and 3 <= median_irr <= 6 else "fail"
    return _result("V6", site, status, "Season medians compared with published rice reference water and wheat irrigation ranges.",
                   n=len(wheat), value={"Rice ET0 (mm)": median_et, "Wheat irrigations": median_irr})


def _soil_moisture(site: Site, current):
    if site.site_id != "malawi":
        return _result("V7", site, "not_run", "The satellite root-zone wetness check is specific to the Malawi demo.")
    if not SMAP.is_file():
        return _result("V7", site, "not_run", "NASA Earthdata sign-in is required to request the AppEEARS sample.")
    smap = pd.read_parquet(SMAP)
    wetness = pd.concat([pd.Series(1 - season.daily.dr_mm / season.daily.taw_mm, index=season.dates)
                         for season in current.phases[0]]).rename("model")
    observed = smap.set_index(pd.to_datetime(smap["date"])) if "date" in smap.columns else smap
    matched = pd.concat([wetness, observed["sm_rootzone_wetness"].rename("smap")], axis=1).dropna().loc["2015":"2024"]
    if len(matched) < 2:
        return _result("V7", site, "not_run", "There are too few matching daily values to estimate agreement.")
    anomalous = matched - matched.groupby(matched.index.strftime("%m-%d")).transform("mean")
    value = float(spearmanr(anomalous["model"], anomalous["smap"]).statistic)
    if not np.isfinite(value):
        return _result("V7", site, "not_run", "The soil wetness anomalies have no variation to compare.")
    return _result("V7", site, "pass" if value >= .5 else "caveat" if value >= .3 else "fail",
                   "Compared matched daily values after removing the typical wetness for each date.", n=len(anomalous), value=value)


def _modis_water(site: Site, current, satellite):
    if satellite is None or satellite.empty:
        return _result("V8", site, "not_run", "The ORNL satellite water-use product is unavailable for this run.")
    biases = []
    first_obs = satellite.index.min()
    last_obs = satellite.index.max()
    coverage_through = last_obs + timedelta(days=min(7, (pd.Timestamp(last_obs.year, 12, 31) - last_obs).days))
    for season in current.phases[0]:
        if first_obs > season.dates[0] or coverage_through < season.dates[-1]:
            continue
        observed = satellite.loc[season.dates[0]:season.dates[-1], "et_mm"].dropna()
        model = pd.Series(season.daily.etc_adj, index=season.dates)
        pairs = []
        for date, value in observed.items():
            days = min(8, (pd.Timestamp(year=date.year+1, month=1, day=1)-date).days)
            daily = model.loc[date:date + timedelta(days=days-1)]
            if len(daily) == days:
                pairs.append((float(value), float(daily.sum())))
        totals = np.asarray(pairs).sum(axis=0) if pairs else (0, 0)
        if totals[0] > 0:
            biases.append(100 * (totals[1] - totals[0]) / totals[0])
    if not biases:
        return _result("V8", site, "not_run", "There are no complete matching satellite water-use periods.")
    return _result("V8", site, "caveat", "Model minus satellite, divided by satellite water use. MOD16 is a lower bound where fields are irrigated.",
                   n=len(biases), value=float(np.median(biases)))


def build_validation(site: Site, climate, runs: Mapping[str, RotationRun], crops: Mapping[str, Crop],
                     *, phenology=None, modis_et=None, assumed_calendar=None) -> list[ValidationResult]:
    current = next(run for run in runs.values() if run.rotation.is_current)
    example = float(example_18().et0)
    v1 = _result("V1", site, "pass" if abs(example - 3.9) <= .1 else "fail", "Reproduces the reference calculation in Brussels.", n=1, value=example)
    v2 = _compare_tiers(site, climate, runs, crops)
    v3 = _calendar_validation(site, assumed_calendar or current.rotation, crops, phenology)
    years = [year for run in runs.values() for phase in run.phases for year in phase]
    residual = max(year.result.wb_residual_max_mm for year in years)
    v4 = _result("V4", site, "pass" if residual < .1 else "fail", "Largest daily difference between inputs, outputs and modelled storage.",
                 n=sum(len(year.dates) for year in years), value=residual)
    return [v1, v2, v3, v4, _fires(site, current, crops), _sanity(site, climate, current),
            _soil_moisture(site, current), _modis_water(site, current, modis_et)]
