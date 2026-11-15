import json
from dataclasses import asdict, replace
from datetime import timedelta
from functools import lru_cache
from statistics import median

import pandas as pd
from requests import RequestException

from basalt.calendar_utils import calendar_windows, validate_rotation
from basalt.climate.power import fetch_power, load_climate
from basalt.climate.trends import annual_trends
from basalt.config import DEMO, DEMO_COORDS, YEARS, in_punjab
from basalt.contracts import Constraints, Rotation, Scenario, Site
from basalt.decision.levers import make_current, propose_levers
from basalt.decision.replay import replay
from basalt.decision.stability import stability
from basalt.explain.cards import build_card
from basalt.explain.patterns import field_patterns
from basalt.global_tier.ggcmi import default_season_start, ggcmi_cell, local_calendars
from basalt.global_tier.grace import regional_trend
from basalt.knowledge.loader import load_crops, load_punjab_rotations, load_soils, validated
from basalt.satellite.validate import build_validation
from basalt.soil.soilgrids import SoilGridsUnavailable, fetch_soilgrids
from basalt.strata_data import encode_strata


@lru_cache(maxsize=2)
def load_demo(site_id: str) -> dict:
    if site_id not in DEMO_COORDS:
        raise ValueError("Unknown demo location")
    with (DEMO / site_id / "bundle.json").open(encoding="utf-8") as stream:
        return json.load(stream)


def _find_soil(site_id: str, lat: float, lon: float, soil_class):
    if soil_class is not None:
        if soil_class not in load_soils():
            raise ValueError("Choose a soil type in the field settings.")
        return soil_class, "user"
    if site_id in DEMO_COORDS:
        path = DEMO / site_id / "soil.json"
        if path.is_file():
            return json.loads(path.read_text())["soil_class"], "soilgrids"
        if site_id == "ludhiana":
            return "sandy_loam", "demo_default"
        raise ValueError("SoilGrids texture is unavailable for the Malawi demo.")
    try:
        return fetch_soilgrids(lat, lon)["soil_class"], "soilgrids"
    except SoilGridsUnavailable as error:
        raise SoilGridsUnavailable("SoilGrids is unavailable. Choose the soil type to see this field.") from error


def _choose_irrigation(lat, lon, calibrated, irrigated):
    if irrigated is not None:
        return irrigated
    if calibrated:
        return True
    def area(system):
        rows = local_calendars(lat, lon, system)
        return sum(row.harvested_frac or 0 for row in rows)
    return area(True) > area(False)


def _setup(site_id, name, lat, lon, crop_ids, irrigated, soil_class, crops):
    calibrated = in_punjab(lat, lon)
    irrigated = _choose_irrigation(lat, lon, calibrated, irrigated)
    texture, soil_source = _find_soil(site_id, lat, lon, soil_class)
    calendars = ()
    reasons = {}
    if calibrated:
        presets = load_punjab_rotations()
        selected = (crop_ids or ("pb_rw",))[0]
        if len(crop_ids or ()) > 1 or selected not in presets:
            raise ValueError("Choose a Punjab rotation preset.")
        rotations = tuple(replace(preset, is_current=key == selected,
                                  lever="current" if key == selected else ("swap_weak_link" if key == "pb_rw" else preset.lever))
                          for key, preset in presets.items())
        rotations = tuple(sorted(rotations, key=lambda rotation: not rotation.is_current))
        reasons = {rotation.rotation_id: [{"rule": "preset", "name": rotation.name, "notes": rotation.notes}]
                   for rotation in rotations if not rotation.is_current}
        options = {item.rotation_id: item.name for item in presets.values()}
        crop_ids = (selected,)
        calendar_source = "pau"
        start = "06-01"
    else:
        calendars = local_calendars(lat, lon, irrigated)
        options = {row.crop_id: crops[row.crop_id].name for row in calendars}
        if not options:
            raise ValueError("No supported farm crop calendar is available at this pin for the selected water source.")
        if not crop_ids:
            crop_ids = ("maize",) if site_id == "malawi" and "maize" in options else (next(iter(options)),)
        if not set(crop_ids) <= options.keys():
            raise ValueError("Choose the current crops from the crops grown here.")
        start = default_season_start(next(row for row in calendars if row.crop_id == crop_ids[0]))
        rotations = (make_current(crop_ids, calendars),)
        calendar_source = "ggcmi"
    site = Site(site_id, name, lat, lon, "calibrated" if calibrated else "global", texture, soil_source,
                irrigated, start, None if calibrated else ggcmi_cell(lat, lon))
    validate_rotation(rotations[0], crops, start)
    setup = {"soil_classes": list(load_soils()), "crop_options": options, "current_crop_ids": list(crop_ids),
             "soil_class": texture, "irrigated": irrigated}
    return site, rotations, reasons, setup, calendars, calendar_source


def _satellite(site: Site, *, online: bool = False) -> tuple:
    if site.site_id in DEMO_COORDS:
        files = [DEMO / site.site_id / f"{name}.parquet" for name in ("ndvi", "modis_et")]
        return tuple(pd.read_parquet(path) if path.is_file() else None for path in files)
    if not online:
        return None, None
    from basalt.satellite.ornl import fetch_ndvi
    try:
        return fetch_ndvi(site.lat, site.lon), None
    except (RequestException, ValueError, OSError, RuntimeError):
        return None, None


def _phenology(ndvi, start):
    if ndvi is None:
        return None
    from basalt.satellite.phenology import detect_phenology
    return detect_phenology(ndvi, start)


def _adjust_calendar(rotation, crops, start, phenology):
    dates_by_slot = {slot.crop_id: [] for slot in rotation.years[0]}
    for window in calendar_windows(rotation, crops, start, YEARS):
        matches = phenology["seasons"].get(window.season, [])
        if not matches:
            continue
        initial, developing, middle, _ = window.stage_days
        expected_peak = window.sow + timedelta(days=initial + developing + middle // 2)
        match = min(matches, key=lambda period: abs((pd.Timestamp(period["peak"]) - expected_peak).days))
        peak_delta = (pd.Timestamp(match["peak"]) - expected_peak).days
        sow_delta = (pd.Timestamp(match["sow_est"]) - window.sow).days
        dates_by_slot[window.crop.crop_id].append((peak_delta, sow_delta))
    shifts = {}
    for crop_id, pairs in dates_by_slot.items():
        if pairs and abs(median(pair[0] for pair in pairs)) > 30:
            shifts[crop_id] = timedelta(days=round(median(pair[1] for pair in pairs)))
    if not shifts:
        return rotation
    shifted = []
    for slot in rotation.years[0]:
        shift = shifts.get(slot.crop_id, timedelta(0))
        sow, harvest = [(pd.Timestamp(f"2001-{date}") + shift).strftime("%m-%d") for date in (slot.sow, slot.harvest)]
        shifted.append(replace(slot, sow=sow, harvest=harvest))
    candidate = replace(rotation, years=(tuple(shifted),))
    try:
        validate_rotation(candidate, crops, start)
    except ValueError:
        return rotation
    return candidate


def _datasets(site, ndvi, modis_et, grace, checks):
    names = []
    if site.tier == "global":
        names.append("GGCMI Phase 3 v1.01 and MapSPAM 2010")
    if ndvi is not None:
        names.append("MODIS MOD13Q1 v061 via ORNL DAAC")
    if modis_et is not None:
        names.append("MODIS MOD16A2GF v061 via ORNL DAAC")
    if grace.get("trend_cm_per_yr") is not None:
        names.append(grace.get("dataset", "GRACE/GRACE-FO"))
    names.extend(check["dataset"] for check in checks if check["check_id"] in {"V5", "V7"} and check["n"])
    return names


def _assemble(site_id, name, lat, lon, climate, *, crop_ids=None, irrigated=None, soil_class=None,
              constraints=Constraints(), scenario=Scenario(), online=False, base=None) -> dict:
    crops = load_crops()
    site, rotations, why, setup, calendars, calendar_source = _setup(
        site_id, name, lat, lon, crop_ids, irrigated, soil_class, crops,
    )
    soils = load_soils()
    soil = soils[site.soil_class]
    ndvi, modis_et = _satellite(site, online=online) if base is None else (None, None)
    phenology = _phenology(ndvi, site.season_year_start)
    assumed_calendar = rotations[0]
    if site.tier == "global" and phenology is not None:
        current = _adjust_calendar(assumed_calendar, crops, site.season_year_start, phenology)
        if current != rotations[0]:
            rotations = (current,)
            calendar_source = "ndvi"
    rejected = []
    if base is None and site.tier == "global":
        gaps = {key: crop for key, crop in crops.items() if crop.gdd_req is not None}
        outcome = propose_levers(site, rotations[0], climate, crops, gaps, calendars, soil, constraints)
        rotations += outcome.rotations
        why.update(outcome.why)
        rejected = outcome.rejected
    if base is not None:
        rotations = tuple(validated(row, Rotation) for row in base["rotations"])
        why, rejected = base["why"], base["rejections"]
        calendar_source = base["field_story"]["calendar_source"]
    current = rotations[0]
    evidence, runs = replay(site, climate, rotations, crops, soil, constraints, scenario=scenario, why=why)
    if base is None:
        trends = annual_trends(climate, site, current, crops)
        grace = regional_trend(lat, lon)
        validations = build_validation(site, climate, runs, crops, phenology=phenology, modis_et=modis_et,
                                       assumed_calendar=assumed_calendar)
        story = {"site": asdict(site), "tier": site.tier, "current_rotation_id": current.rotation_id,
                 "ndvi_seasons_detected": phenology["n_seasons"] if phenology else 0, "calendar_source": calendar_source,
                 "patterns": field_patterns(runs[current.rotation_id], crops, trends, grace), "trends": trends, "grace": grace}
        badges = stability(site, climate, rotations, crops, soil, soils, constraints,
                           baseline=runs if scenario == Scenario() else None)
        datasets = _datasets(site, ndvi, modis_et, grace, validations)
    else:
        story, validations = base["field_story"], base["validation"]
        badges = {record["rotation_id"]: record["stability"] for record in base["evidence"]}
        datasets = list(dict.fromkeys(dataset for row in base["evidence"] for dataset in row["datasets"]))
    for row in evidence:
        row["stability"] = badges[row["rotation_id"]]
        row["datasets"] = list(dict.fromkeys(row["datasets"] + datasets))
    cards = {row["rotation_id"]: build_card(row, evidence[0], irrigated=site.irrigated,
                                           calendar_source=calendar_source) for row in evidence}
    setup.update(asdict(constraints))
    return {"field_story": story, "evidence": evidence, "cards": cards, "setup": setup, "validation": validations,
            "strata": {key: encode_strata(run, crops, site.season_year_start) for key, run in runs.items()},
            "rotations": [asdict(rotation) for rotation in rotations], "rejections": rejected, "why": why}


def analyze_location(lat: float, lon: float, *, soil_class=None, irrigated=None, crop_ids=None,
                     constraints=Constraints(), scenario=Scenario()) -> dict:
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Choose a valid latitude and longitude.")
    climate = fetch_power(lat, lon)
    return _assemble("custom", f"{lat:.4f}, {lon:.4f}", lat, lon, climate, crop_ids=crop_ids,
                     irrigated=irrigated, soil_class=soil_class, constraints=constraints, scenario=scenario, online=True)


def precompute_demo(site_id: str) -> dict:
    name, lat, lon = DEMO_COORDS[site_id]
    climate = load_climate(DEMO / site_id / "climate.parquet")
    return _assemble(site_id, name, lat, lon, climate, irrigated=(site_id == "ludhiana"))


def demo_scenario(site_id: str, scenario: Scenario = Scenario(), *, soil_class=None, irrigated=None,
                  crop_ids=None, constraints=Constraints()) -> dict:
    baseline = load_demo(site_id)
    setup = baseline["setup"]
    unchanged = ((soil_class is None or soil_class == setup["soil_class"])
                 and (irrigated is None or irrigated == setup["irrigated"])
                 and (crop_ids is None or list(crop_ids) == setup["current_crop_ids"])
                 and constraints == Constraints())
    if unchanged and scenario == Scenario():
        return baseline
    name, lat, lon = DEMO_COORDS[site_id]
    climate = load_climate(DEMO / site_id / "climate.parquet")
    return _assemble(site_id, name, lat, lon, climate, crop_ids=crop_ids, irrigated=setup["irrigated"] if irrigated is None else irrigated,
                     soil_class=None if soil_class == setup["soil_class"] else soil_class,
                     constraints=constraints, scenario=scenario, base=baseline if unchanged else None)
