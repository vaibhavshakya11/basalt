from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import timedelta

import numpy as np
import pandas as pd

from basalt.calendar_utils import calendar_windows, doy_month_day
from basalt.config import YEARS
from basalt.contracts import (
    ClimateTable, Constraints, Crop, CropSlot, LocalCalendar, Priorities, Rotation, RotationRun, Site, Soil,
)
from basalt.decision.replay import arrows_for, erosion_reference, paired_wins
from basalt.physics.simulate import run_rotation


@dataclass(frozen=True)
class LeverOutcome:
    rotations: tuple[Rotation, ...]
    why: dict[str, list[dict]]
    rejected: list[dict[str, str]]


def make_current(crop_ids: Sequence[str], calendars: Sequence[LocalCalendar]) -> Rotation:
    by_crop = {calendar.crop_id: calendar for calendar in reversed(calendars)}
    slots = tuple(CropSlot(crop_id, doy_month_day(by_crop[crop_id].plant_doy),
                          doy_month_day(by_crop[crop_id].maturity_doy)) for crop_id in crop_ids)
    name = "Continuous " + crop_ids[0].replace("_", " ") if len(slots) == 1 else "Current rotation"
    return Rotation("global_current", name, "current", 1, (slots,), True, "")


def _gap_windows(site: Site, current: Rotation, crops: Mapping[str, Crop], years: Sequence[int]):
    windows = calendar_windows(current, crops, site.season_year_start, range(years[0], years[-1]+2))
    gaps = {}
    for previous, following in zip(windows, windows[1:]):
        if previous.season not in years:
            continue
        key = (previous.crop.crop_id, previous.sow.strftime("%m-%d"))
        gaps.setdefault(key, []).append((previous.harvest + timedelta(days=5), following.sow - timedelta(days=5)))
    return max(gaps.values(), key=lambda group: np.median([(hi-lo).days+1 for lo, hi in group]), default=[])


def _suitable_days(climate: ClimateTable, windows: Sequence[tuple[pd.Timestamp, pd.Timestamp]], crop: Crop):
    lengths = []
    for start, end in windows:
        weather = climate.loc[start:end]
        if len(weather) < crop.min_window_days or (crop.frost_sensitive and weather.tmin.le(crop.frost_tmin_c).any()):
            continue
        heat_units = ((weather.tmax + weather.tmin) / 2 - crop.tbase_c).clip(lower=0).cumsum()
        viable = np.flatnonzero(heat_units.to_numpy() >= crop.gdd_req)
        if not len(viable):
            continue
        finish = int(viable[0]) + 1
        initial, develop, middle, _ = crop.stage_fracs
        mid_start = int((initial + develop) * finish)
        mid_end = int((initial + develop + middle) * finish)
        if weather.tmax.iloc[mid_start:mid_end].ge(crop.tcrit_heat_c).sum() <= 3:
            lengths.append(finish)
    return lengths


def _gap_passes_water(run: RotationRun, crop_id: str) -> bool:
    proportions = []
    for season in run.phases[0]:
        crop = (season.daily.crop_id == crop_id) & (season.daily.stage == "mid")
        if crop.any():
            proportions.append(float(season.daily.dry_stress_event[crop].mean()))
    return bool(proportions) and sum(value < .3 for value in proportions) >= 2 * len(proportions) / 3


def _fill_gap(site, current, climate, crops, gap_crops, evaluate, years):
    windows = _gap_windows(site, current, crops, years)
    if not windows:
        return None, None, "No bare window could be identified."
    start, end = windows[0]
    for crop in gap_crops.values():
        suitable = _suitable_days(climate, windows, crop)
        if len(suitable) < .8 * len(years):
            continue
        length = int(np.median(suitable))
        if any(length > (hi-lo).days+1 for lo, hi in windows):
            continue
        slot = CropSlot(crop.crop_id, start.strftime("%m-%d"), (start + timedelta(days=length-1)).strftime("%m-%d"))
        candidate = Rotation("global_gap", f"{current.name.capitalize()} + {crop.name.lower()}", "fill_the_gap",
                             1, (current.years[0] + (slot,),), False, "")
        try:
            run, _ = evaluate(candidate)
        except ValueError:
            continue
        if site.irrigated or _gap_passes_water(run, crop.crop_id):
            why = {"rule": "fill_the_gap", "bare_days": (end-start).days+11, "window_start": slot.sow,
                   "window_end": end.strftime("%m-%d"), "crop": crop.name,
                   "pct": round(100*len(suitable)/len(years)), "n": len(years)}
            return candidate, why, None
    return None, None, "No catch crop met the local window, warmth and water checks often enough."


def _weak_slot(current_run: RotationRun) -> tuple[str, str, int]:
    crop_ids = [slot.crop_id for slot in current_run.rotation.years[0]]
    results = []
    for crop_id in crop_ids:
        hits = {"heat at flowering": 0, "frost": 0, "dry spells": 0}
        et = 0.
        for season in current_run.phases[0]:
            daily = season.daily
            selected = daily.crop_id == crop_id
            in_mid = selected & (daily.stage == "mid")
            hits["heat at flowering"] += int(daily.heat_event[selected].sum() >= 3)
            hits["frost"] += int(daily.frost_event[selected].any())
            hits["dry spells"] += int(in_mid.any() and daily.dry_stress_event[in_mid].mean() >= .3)
            et += float(daily.etc_adj[selected].sum())
        main = max(hits, key=hits.get)
        results.append((sum(hits.values()), et, crop_id, main, hits[main]))
    _, _, crop_id, event, count = max(results)
    return crop_id, event, count


def _fit_calendar(site: Site, current: Rotation, crops: Mapping[str, Crop],
                  crop_id: str, calendar: LocalCalendar) -> CropSlot | None:
    windows = calendar_windows(current, crops, site.season_year_start, range(2000, 2003))
    index = next(i for i, w in enumerate(windows) if w.season == 2001 and w.crop.crop_id == crop_id)
    previous, slot, following = windows[index-1:index+2]
    original = doy_month_day(calendar.plant_doy)
    planting = min((pd.Timestamp(f"{year}-{original}") for year in range(slot.sow.year-1, slot.sow.year+2)),
                   key=lambda date: abs((slot.sow-date).days))
    allowed_start = previous.harvest + timedelta(days=7)
    allowed_end = following.sow - timedelta(days=7)
    if len(current.years[0]) == 1:
        allowed_start = max(allowed_start, slot.sow - timedelta(days=21))
        allowed_end = min(allowed_end, slot.harvest + timedelta(days=21))
    lower = max(planting - timedelta(days=21), allowed_start)
    upper = min(planting + timedelta(days=21), allowed_end - timedelta(days=calendar.season_len-1))
    if lower > upper:
        return None
    sow = min(max(planting, lower), upper)
    harvest = sow + timedelta(days=calendar.season_len-1)
    return CropSlot(calendar.crop_id, sow.strftime("%m-%d"), harvest.strftime("%m-%d"))


def _propose(site, current, crops, calendars, evaluate, current_run, priorities, years):
    weak, event, hits = _weak_slot(current_run)
    swap, alternating = [], []
    crop_ids = {slot.crop_id for slot in current.years[0]}
    ranking = {"soil": priorities.soil, "water": priorities.water, "risk": priorities.risk}
    for calendar in calendars:
        crop = crops.get(calendar.crop_id)
        if crop is None or crop.crop_id in crop_ids:
            continue
        slot = _fit_calendar(site, current, crops, weak, calendar)
        if slot is None:
            continue
        changed = tuple(slot if original.crop_id == weak else original for original in current.years[0])
        alternatives = [(swap, Rotation(f"global_swap_{crop.crop_id}", " and ".join(crops[s.crop_id].name for s in changed),
                                       "swap_weak_link", 1, (changed,), False, ""),
                         {"rule": "swap_weak_link" if hits else "swap_no_risk", "weak_crop": crops[weak].name, "risk_type": event,
                          "k": hits, "n": len(years), "new_crop": crop.name})]
        if len(crop_ids) == 1 and crop.crop_id in {"soybean", "groundnut", "beans", "pea"}:
            alternating_crop = Rotation(f"global_turns_{crop.crop_id}", f"{crops[weak].name} alternating with {crop.name.lower()}",
                                        "take_turns", 2, (current.years[0], (slot,)), False, "")
            alternatives.append((alternating, alternating_crop, {"rule": "take_turns", "legume": crop.name}))
        for choices, candidate, why in alternatives:
            try:
                _, wins = evaluate(candidate)
            except ValueError:
                continue
            choices.append((sum(ranking[axis]*wins[axis]["better"] for axis in ranking), candidate, why))
    return (max(swap, key=lambda row: row[0], default=None),
            max(alternating, key=lambda row: row[0], default=None))


def propose_levers(site: Site, current: Rotation, climate: ClimateTable,
                   crops: Mapping[str, Crop], gap_crops: Mapping[str, Crop],
                   calendars: Sequence[LocalCalendar], soil: Soil, constraints: Constraints = Constraints(),
                   priorities: Priorities = Priorities(), *, years: Sequence[int] = YEARS,
                   run_candidate: Callable[[Rotation], RotationRun] | None = None) -> LeverOutcome:
    """Offer only rotation changes that pass calendar and local feasibility checks."""
    if current.cycle_years != 1:
        return LeverOutcome((), {}, [{"lever": "take_turns", "reason": "The current rotation already spans multiple years."}])
    all_crops = {**crops, **gap_crops}
    baseline = run_rotation(site, climate, current, all_crops, soil, constraints, years=years)
    reference = erosion_reference(baseline)

    def evaluate(candidate):
        run = run_candidate(candidate) if run_candidate else run_rotation(
            site, climate, candidate, all_crops, soil, constraints, years=years, erosion_ref=reference,
        )
        return run, paired_wins(baseline.seasons, run.seasons, site.irrigated)

    gap, gap_why, reason = _fill_gap(site, current, climate, all_crops, gap_crops, evaluate, years)
    swap, turns = _propose(site, current, all_crops, calendars, evaluate, baseline, priorities, years)
    rejected = []
    choices = []
    if gap:
        choices.append((gap, gap_why))
    else:
        rejected.append({"lever": "fill_the_gap", "reason": reason})
    for choice, lever, explanation in [
        (swap, "swap_weak_link", "No other supported crop grown here fits the same slot."),
        (turns, "take_turns", "This lever needs one current crop and a locally grown legume that fits its season."),
    ]:
        if choice:
            choices.append(choice[1:])
        else:
            rejected.append({"lever": lever, "reason": explanation})
    if swap and (gap or turns):
        swap_rotation = swap[1]
        if gap:
            new_slot = next(slot for slot in gap.years[0] if slot not in current.years[0])
            combined = replace(swap_rotation, rotation_id="global_combine", name=f"{swap_rotation.name} + {all_crops[new_slot.crop_id].name.lower()}",
                               lever="combine", years=(swap_rotation.years[0] + (new_slot,),))
            partner = "Fill the gap"
        else:
            turns_rotation = turns[1]
            combined = replace(turns_rotation, rotation_id="global_combine",
                               name=f"{swap_rotation.name} alternating with {all_crops[turns_rotation.years[1][0].crop_id].name.lower()}",
                               lever="combine", years=(swap_rotation.years[0], turns_rotation.years[1]))
            partner = "Take turns"
        repeated = combined.cycle_years == 2 and combined.years[0] == combined.years[1]
        try:
            if repeated:
                raise ValueError("Both years are the same")
            evaluate(combined)
        except ValueError:
            rejected.append({"lever": "combine", "reason": "The two changes overlap or use the same crop in both years."})
        else:
            choices.append((combined, {"rule": "combine", "lever1": "Swap the weak link", "lever2": partner}))
    else:
        rejected.append({"lever": "combine", "reason": "The two changes needed for this option did not both pass."})
    if len(choices) > 3:
        fewest = min(range(len(choices)), key=lambda i: sum(
            arrow == "better" for arrow in arrows_for(evaluate(choices[i][0])[1]).values()
        ))
        rejected.append({"lever": choices[fewest][0].lever, "reason": "Three other feasible options ranked ahead in the replay."})
        del choices[fewest]
    return LeverOutcome(tuple(rotation for rotation, _ in choices),
                        {rotation.rotation_id: [why] for rotation, why in choices}, rejected)
