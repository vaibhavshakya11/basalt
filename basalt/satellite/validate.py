from collections.abc import Mapping
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.stats import spearmanr

from basalt.calendar_utils import calendar_windows, stage_lengths, validate_rotation
from basalt.climate.et0 import example_18
from basalt.config import DATA, YEARS
from basalt.contracts import Constraints, Crop, RotationRun, Site, ValidationResult
from basalt.decision.replay import compare_runs, replay_runs
from basalt.global_tier.ggcmi import calendar_slot, ggcmi_cell, local_calendars
from basalt.knowledge.loader import load_soils

FIRMS = DATA / "firms" / "ludhiana_pentads.parquet"
SMAP = DATA / "smap" / "malawi_smap_l4.parquet"
CHECKS = {
    "V1": ("FAO-56 Example 18", "1998", "6 July", "Reference water use", "mm/day", "3.9 ± 0.1 mm/day"),
    "V2": ("GGCMI Phase 3, PAU crop calendars and FAO-56", "GGCMI 1.01", "2001 to 2024", "Global and calibrated arrow agreement", "%", "At least 75% agreement meets the numerical threshold. Calendar infeasibility remains a caveat."),
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


GLOBAL_CROP_FOR = {"rice_pb": "rice", "wheat_pb": "wheat_winter", "maize_pb": "maize", "moong_pb": "mungbean"}


def _matched_crop_parameters(crops):
    matched = {}
    for local_id, global_id in GLOBAL_CROP_FOR.items():
        generic = crops[global_id]
        # Use the PAU duration for an implicit harvest, including seasons that cross a leap day.
        stages = stage_lengths(generic, sum(stage_lengths(crops[local_id])))
        matched[local_id] = replace(generic, crop_id=local_id, stage_days=stages)
    return matched


def _raw_calendars(site, rotations, crops):
    regional_ids = set(GLOBAL_CROP_FOR.values()) - {"mungbean"}
    available = {row.crop_id: row for row in local_calendars(site.lat, site.lon, True, grown_only=False)
                 if row.crop_code != "ri2"}
    if not regional_ids <= available.keys():
        return None, "The GGCMI cell lacks irrigated dates for at least one crop."
    slots = {crop_id: calendar_slot(available[crop_id]) for crop_id in regional_ids}
    raw_crops = dict(crops)
    raw_crops["mungbean"] = replace(crops["mungbean"], stage_days=stage_lengths(
        crops["mungbean"], sum(stage_lengths(crops["moong_pb"]))))
    plan = tuple(replace(rotation, years=tuple(
        tuple(slots[GLOBAL_CROP_FOR[slot.crop_id]] if slot.crop_id != "moong_pb" else replace(slot, crop_id="mungbean")
              for slot in group) for group in rotation.years
    )) for rotation in rotations)
    feasible = []
    for rotation in plan:
        try:
            validate_rotation(rotation, raw_crops, site.season_year_start)
        except ValueError:
            continue
        feasible.append(rotation)
    if len(feasible) == len(plan):
        return (plan, raw_crops), ""
    rice, wheat = slots["rice"], slots["wheat_winter"]
    rice_end = pd.Timestamp(f"2001-{rice.harvest}").strftime("%d %B")
    wheat_start = pd.Timestamp(f"2001-{wheat.sow}").strftime("%d %B")
    detail = (f"Unadjusted GGCMI dates fit {len(feasible)} of {len(plan)} rotations. "
              f"Rice ends on {rice_end} and wheat starts on {wheat_start}. The shared-calendar check isolates "
              "the effect of global crop parameters.")
    return None, detail


def _agreement(site, calibrated_runs, global_runs):
    calibrated = compare_runs(calibrated_runs, site.irrigated)
    alternative = compare_runs(global_runs, site.irrigated)
    matches = {key: sum(arrow == alternative[key][axis] for axis, arrow in row.items())
               for key, row in calibrated.items()}
    n = sum(map(len, calibrated.values()))
    current = next(key for key, run in calibrated_runs.items() if run.rotation.is_current)
    total_matches = sum(matches.values())
    no_baseline = n - len(calibrated[current])
    metrics = {"Arrow agreement (%)": 100 * total_matches / n,
               "Matching arrows": total_matches, "Compared arrows": n,
               "Matching alternative arrows": total_matches - matches[current],
               "Compared alternative arrows": no_baseline}
    for field, label in (("et_mm", "Median ET difference (mm/year)"),
                         ("soil_score", "Median soil-score difference (points)")):
        gaps = []
        for key, run in calibrated_runs.items():
            baseline = np.median([getattr(season, field) for season in run.seasons])
            generic = np.median([getattr(season, field) for season in global_runs[key].seasons])
            gaps.append(abs(baseline - generic))
        metrics[label] = float(np.median(gaps))
    return metrics, n


def _compare_tiers(site, climate, runs, crops, constraints=Constraints()):
    if site.site_id != "ludhiana":
        return _result("V2", site, "not_run", "The calibrated comparison applies to Ludhiana.")
    if not site.irrigated:
        return _result("V2", site, "not_run", "The Ludhiana comparison uses irrigated crop calendars.")
    rotations = tuple(run.rotation for run in runs.values())
    regional, calendar_note = _raw_calendars(site, rotations, crops)
    global_site = replace(site, tier="global", ggcmi_cell=ggcmi_cell(site.lat, site.lon))
    soil = load_soils()[site.soil_class]
    if regional:
        global_rotations, global_crops = regional
        note = "Used complete GGCMI rotation dates with the same weather, soil and field settings."
    else:
        global_rotations, global_crops = rotations, _matched_crop_parameters(crops)
        note = ("Both runs used the same PAU planting and harvest dates, weather, soil and field settings. "
                f"{calendar_note}")
    global_runs = replay_runs(global_site, climate, global_rotations, global_crops, soil, constraints)
    values, n = _agreement(site, runs, global_runs)
    percent = values["Arrow agreement (%)"]
    status = "fail" if percent < 50 else "pass" if regional and percent >= 75 else "caveat"
    return _result("V2", site, status, note, n=n, value=values)


def _calendar_validation(site: Site, rotation, crops, phenology):
    if phenology is None:
        return _result("V3", site, "not_run", "This replay does not have a local MODIS greenness series.")
    if not phenology["seasons"]:
        return _result("V3", site, "not_run", "The MODIS series did not identify a growing period suitable for comparison.")
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
        return _result("V7", site, "not_run", "The NASA AppEEARS wetness export has not been added to this replay yet.")
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
                   ("For each calendar date, the check removes the usual soil wetness from each series before it compares "
                    "the paired days. The 9 km SMAP product combines satellite measurements with a land model."),
                   n=len(anomalous), value=value)


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
                     *, phenology=None, modis_et=None, assumed_calendar=None, constraints=Constraints()) -> list[ValidationResult]:
    current = next(run for run in runs.values() if run.rotation.is_current)
    example = float(example_18().et0)
    v1 = _result("V1", site, "pass" if abs(example - 3.9) <= .1 else "fail", "Reproduces the reference calculation in Brussels.", n=1, value=example)
    v2 = _compare_tiers(site, climate, runs, crops, constraints)
    v3 = _calendar_validation(site, assumed_calendar or current.rotation, crops, phenology)
    years = [year for run in runs.values() for phase in run.phases for year in phase]
    residual = max(year.result.wb_residual_max_mm for year in years)
    v4 = _result("V4", site, "pass" if residual < .1 else "fail", "Largest daily difference between inputs, outputs and modelled storage.",
                 n=sum(len(year.dates) for year in years), value=residual)
    return [v1, v2, v3, v4, _fires(site, current, crops), _sanity(site, climate, current),
            _soil_moisture(site, current), _modis_water(site, current, modis_et)]
