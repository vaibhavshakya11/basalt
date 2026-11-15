import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from functools import lru_cache

import numpy as np
import pandas as pd

from basalt.calendar_utils import calendar_windows
from basalt.climate.power import POWER_SOURCE
from basalt.climate.scenario import apply_scenario
from basalt.config import YEARS
from basalt.contracts import (
    Arrow, ClimateTable, Constraints, Crop, Evidence, Metric, ModelParameters,
    Rotation, RotationRun, Scenario, SeasonResult, Site, Soil, Wins,
)
from basalt.knowledge.loader import load_assumptions, read_yaml
from basalt.physics.simulate import apply_erosion_reference, run_rotation
from basalt.physics.soilhealth import FACTORS

AXES = ("soil", "water", "risk")
METRICS = {
    "soil_score": ("0-100", "higher_better"),
    "et_mm": ("mm/yr", "lower_better"),
    "irr_net_mm": ("mm/yr", "context"),
    "irr_gross_mm": ("mm/yr", "lower_better"),
    "irr_events": ("events/yr", "context"),
    "rain_mm": ("mm/yr", "context"),
    "runoff_mm": ("mm/yr", "context"),
    "deep_perc_mm": ("mm/yr", "context"),
    "risk_hits": ("crop events/yr", "lower_better"),
    "heat_days": ("days/yr", "lower_better"),
    "heat_hit_crops": ("crop events/yr", "lower_better"),
    "frost_days": ("days/yr", "lower_better"),
    "frost_hit_crops": ("crop events/yr", "lower_better"),
    "dry_stress_frac": ("0-1", "lower_better"),
    "dry_hit_crops": ("crop events/yr", "lower_better"),
    "bare_days": ("days/yr", "lower_better"),
    "erosion_index": ("relative index", "lower_better"),
    "burn_pressure": ("0-1", "lower_better"),
    "wb_residual_max_mm": ("mm/day", "context"),
}


@lru_cache(maxsize=1)
def copy_templates() -> dict:
    """Read basalt's fixed copy templates."""
    return read_yaml("copy.yaml")


def _counts(delta: np.ndarray, margin: float | np.ndarray) -> Wins:
    magnitude = np.abs(delta)
    material = (magnitude > 0) & ((magnitude >= margin) | np.isclose(magnitude, margin, rtol=1e-12, atol=1e-12))
    better = int(np.count_nonzero(material & (delta > 0)))
    worse = int(np.count_nonzero(material & (delta < 0)))
    return {"better": better, "worse": worse, "tie": len(delta) - better - worse}


def paired_wins(
    current: Sequence[SeasonResult], option: Sequence[SeasonResult], irrigated: bool,
) -> dict[str, Wins]:
    """Count material changes against the same historical seasons."""
    if [season.season for season in current] != [season.season for season in option]:
        raise ValueError("Comparisons require the same farming years")

    def series(seasons, metric):
        return np.asarray([getattr(season, metric) for season in seasons])

    water_metric = "et_mm" if irrigated else "dry_stress_frac"
    current_water = series(current, water_metric)
    return {
        "soil": _counts(series(option, "soil_score") - series(current, "soil_score"), 2),
        "water": _counts(current_water - series(option, water_metric), 0.03 * current_water if irrigated else 0.05),
        "risk": _counts(series(current, "risk_hits") - series(option, "risk_hits"), 0),
    }


def arrows_for(wins: Mapping[str, Wins], threshold: int = 16) -> dict[str, Arrow]:
    """Require the configured number of paired wins before changing an arrow."""
    return {
        axis: "better" if count["better"] >= threshold else "worse" if count["worse"] >= threshold else "similar"
        for axis, count in wins.items()
    }


def erosion_reference(current: RotationRun) -> float:
    """Use one current-rotation erosion reference for every option at the site."""
    return float(np.percentile([season.erosion_index for season in current.seasons], 95))


def compare_runs(
    runs: Mapping[str, RotationRun], irrigated: bool, threshold: int = 16,
) -> dict[str, dict[str, Arrow]]:
    """Compare the arrows of already evaluated rotations."""
    current = next(run for run in runs.values() if run.rotation.is_current)
    return {
        rotation_id: arrows_for(paired_wins(current.seasons, run.seasons, irrigated), threshold)
        for rotation_id, run in runs.items()
    }


def _summarize(values: Sequence[float], unit: str, direction: str) -> Metric:
    p10, median, p90 = np.percentile(values, [10, 50, 90])
    return {"p10": float(p10), "median": float(median), "p90": float(p90), "unit": unit, "direction": direction}


def _metrics(seasons: Sequence[SeasonResult]) -> dict:
    metrics = {
        metric: _summarize([getattr(season, metric) for season in seasons], unit, direction)
        for metric, (unit, direction) in METRICS.items()
    }
    metrics["soil_factors"] = {
        factor: _summarize([season.soil_factors[factor] for season in seasons], "0-1", "higher_better")
        for factor in FACTORS
    }
    return metrics


def _verdict(rotation: Rotation, arrows: Mapping[str, Arrow], wins: Mapping[str, Wins], n: int) -> str:
    templates = copy_templates()["verdict"]
    if rotation.is_current:
        return templates["current"]
    phrases = [
        templates["axis"][axis][arrows[axis]].format(k=wins[axis].get(arrows[axis], 0), n=n)
        for axis in AXES
    ]
    if all(arrows[axis] == "similar" for axis in AXES):
        return templates["all_similar"]
    return templates["join"].format(first=phrases[0].capitalize(), second=phrases[1], third=phrases[2])


def _crop_ids(rotation: Rotation) -> tuple[str, ...]:
    return tuple(dict.fromkeys(slot.crop_id for group in rotation.years for slot in group))


def _calendar(site: Site, rotation: Rotation, crops: Mapping[str, Crop], shift_days: int) -> list[dict]:
    windows = calendar_windows(
        rotation, crops, site.season_year_start, range(2001, 2001 + rotation.cycle_years), shift_days=shift_days,
    )
    return [
        {"crop_id": window.crop.crop_id, "sow_doy": window.sow.dayofyear, "harvest_doy": window.harvest.dayofyear,
         "year_in_cycle": window.season - 2001}
        for window in windows
    ]


def _constraints(site: Site, constraints: Constraints, run: RotationRun) -> list[str]:
    flags = []
    violations = sum(season.irr_exceeds_limit for season in run.seasons)
    if violations:
        flags.append(f"needs_more_irrigation_than_available_in_{violations}_of_{len(run.seasons)}")
    if site.tier == "calibrated" and constraints.prefer_assured_market and not {"rice_pb", "wheat_pb"} <= set(_crop_ids(run.rotation)):
        flags.append("assured_market_dropped")
    return flags


def _sources(site: Site, crops: Sequence[Crop], datasets: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
    templates = copy_templates()
    sources = list(dict.fromkeys(source for crop in crops for source in crop.sources))
    sources.extend(templates["model_sources"])
    used = [POWER_SOURCE, templates["calendar_sources"]["pau" if site.tier == "calibrated" else "ggcmi"]]
    if site.soil_source == "soilgrids":
        used.append("SoilGrids 2.0")
    used.extend(datasets)
    assumptions = list(templates["assumptions"]["both"])
    if site.irrigated:
        assumptions.extend(templates["assumptions"]["irrigated"])
    if any(crop.ponded for crop in crops) and site.irrigated:
        assumptions.extend(templates["assumptions"]["puddled"])
    if site.soil_source == "demo_default":
        assumptions.extend(templates["assumptions"]["demo_soil"])
    if any(crop.stage_fracs is not None for crop in crops):
        assumptions.extend(templates["assumptions"]["global"])
    if any(crop.gdd_req is not None for crop in crops):
        assumptions.extend(templates["assumptions"]["gap"])
        scopes = {"global and gap crops", "gap crops"}
    else:
        scopes = {"global and gap crops"} if site.tier == "global" else set()
    assumptions.extend(
        templates["assumptions"]["added"].format(value=entry.value, reason=entry.reason)
        for entry in load_assumptions() if entry.scope == "all fields" or entry.scope in scopes
    )
    return list(dict.fromkeys(used)), list(dict.fromkeys(sources)), assumptions


def _heat_risks(run: RotationRun, site: Site, crops: Mapping[str, Crop], shift_days: int) -> list[str]:
    seasons = [season.season for season in run.seasons]
    heat_hit_years = {crop_id: set() for crop_id in _crop_ids(run.rotation)}
    for phase_index, phase in enumerate(run.phases):
        for crop_id, hits in heat_hit_years.items():
            events = pd.DatetimeIndex(np.concatenate([
                season.dates[(season.daily.crop_id == crop_id) & season.daily.heat_event].to_numpy()
                for season in phase
            ]))
            if len(events) < 3:
                continue
            windows = calendar_windows(run.rotation, crops, site.season_year_start, seasons,
                                       phase=phase_index, shift_days=shift_days)
            for window in windows:
                if window.crop.crop_id == crop_id and np.count_nonzero((events >= window.sow) & (events <= window.harvest)) >= 3:
                    hits.add(window.season)
    return [
        json.dumps({"rule": "heat_phases" if len(run.phases) > 1 else "heat", "crop": crops[crop_id].name,
                    "k": len(hits), "n": len(seasons)})
        for crop_id, hits in heat_hit_years.items() if hits
    ]


def evidence_for_runs(
    site: Site, runs: Mapping[str, RotationRun], crops: Mapping[str, Crop], constraints: Constraints = Constraints(),
    *, scenario: Scenario = Scenario(), shift_days: int = 0, threshold: int = 16,
    why: Mapping[str, Sequence[dict]] | None = None, datasets: Sequence[str] = (),
) -> list[Evidence]:
    """Summarize phase-averaged seasons and paired comparisons into evidence."""
    current = next(run for run in runs.values() if run.rotation.is_current)
    evidence = []
    for run in runs.values():
        rotation = run.rotation
        wins = paired_wins(current.seasons, run.seasons, site.irrigated)
        arrows = arrows_for(wins, threshold)
        crop_library = [crops[crop_id] for crop_id in _crop_ids(rotation)]
        used_datasets, sources, assumptions = _sources(site, crop_library, datasets)
        why_rule = "current" if rotation.is_current else rotation.rotation_id
        fallback = [{"rule": why_rule}] if why_rule in copy_templates()["why"] else []
        reasons = (why or {}).get(rotation.rotation_id, fallback)
        evidence.append(Evidence(
            rotation_id=rotation.rotation_id, name=rotation.name, lever=rotation.lever, is_current=rotation.is_current,
            site_id=site.site_id, tier=site.tier, scenario=asdict(scenario), n_seasons=len(run.seasons),
            season_range=[run.seasons[0].season, run.seasons[-1].season], metrics=_metrics(run.seasons),
            wins_vs_current=wins, arrows=arrows, verdict=_verdict(rotation, arrows, wins, len(run.seasons)),
            stability={"badge": "robust", "drivers": []}, constraints_flags=_constraints(site, constraints, run),
            tags=list(dict.fromkeys(tag for crop in crop_library for tag in crop.tags)),
            calendar=_calendar(site, rotation, crops, shift_days), why=[json.dumps(reason) for reason in reasons],
            gaps=[], risks=_heat_risks(run, site, crops, shift_days), datasets=used_datasets, sources=sources, assumptions_L=assumptions,
        ))
    return evidence


def replay_runs(
    site: Site, climate: ClimateTable, rotations: Sequence[Rotation], crops: Mapping[str, Crop], soil: Soil,
    constraints: Constraints = Constraints(), *, parameters: ModelParameters = ModelParameters(),
    shift_days: int = 0, years: Sequence[int] = YEARS, reuse: Mapping[str, RotationRun] | None = None,
) -> dict[str, RotationRun]:
    """Simulate all rotations and normalize soil factors against the current rotation."""
    if sum(rotation.is_current for rotation in rotations) != 1:
        raise ValueError("Replay requires exactly one current rotation")
    runs = {
        rotation.rotation_id: (reuse or {}).get(rotation.rotation_id)
        or run_rotation(site, climate, rotation, crops, soil, constraints, parameters=parameters,
                        shift_days=shift_days, years=years)
        for rotation in rotations
    }
    current = next(run for run in runs.values() if run.rotation.is_current)
    reference = erosion_reference(current)
    return {
        rotation_id: apply_erosion_reference(run, reference, parameters.soil_weights)
        for rotation_id, run in runs.items()
    }


def replay(
    site: Site, climate: ClimateTable, rotations: Sequence[Rotation], crops: Mapping[str, Crop], soil: Soil,
    constraints: Constraints = Constraints(), *, scenario: Scenario = Scenario(),
    parameters: ModelParameters = ModelParameters(), shift_days: int = 0, years: Sequence[int] = YEARS,
    threshold: int = 16, why: Mapping[str, Sequence[dict]] | None = None, datasets: Sequence[str] = (),
) -> tuple[list[Evidence], dict[str, RotationRun]]:
    """Replay a fixed set of candidate rotations under the same climate scenario."""
    weather = apply_scenario(climate, scenario)
    runs = replay_runs(site, weather, rotations, crops, soil, constraints,
                       parameters=parameters, shift_days=shift_days, years=years)
    rows = evidence_for_runs(site, runs, crops, constraints, scenario=scenario, shift_days=shift_days,
                             threshold=threshold, why=why, datasets=datasets)
    return rows, runs
