from collections import Counter
from itertools import groupby
from math import ceil
from statistics import median

import numpy as np

from basalt.contracts import Crop, RotationRun

EVENT_NAMES = {"heat_event": "heat", "frost_event": "frost", "dry_stress_event": "dry spells"}
STAGE_NAMES = {"ini": "early growth", "dev": "developing canopy", "mid": "mid-season", "late": "late growth"}


def _longest_bare(season):
    # Crop-free stretches may cross the agricultural year boundary.
    bare = season.daily.crop_id == "bare"
    runs = [(start, end) for is_bare, group in groupby(range(len(bare)), key=bare.__getitem__)
            if is_bare for start, *rest in [list(group)] for end in [rest[-1] if rest else start]]
    if not runs:
        return 0, 0, 0
    size = len(bare)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == size - 1:
        runs = [(runs[-1][0], size + runs[0][1]), *runs[1:-1]]
    start, end = max(runs, key=lambda pair: pair[1]-pair[0])
    return end-start+1, start, end % size


def field_patterns(run: RotationRun, crops: dict[str, Crop], trends: list[dict], grace: dict) -> list[dict]:
    patterns = []
    seasons = run.phases[0]
    bare = [_longest_bare(season) for season in seasons]
    if bare and sum(length >= 30 for length, _, _ in bare) >= ceil(.75 * len(bare)):
        length = round(median(row[0] for row in bare))
        representative = min(range(len(bare)), key=lambda i: abs(bare[i][0]-length))
        _, start, end = bare[representative]
        dates = seasons[representative].dates
        date_range = f"{dates[start].strftime('%d %b')} to {dates[end].strftime('%d %b')}"
        patterns.append({"id": "bare", "text": f"Bare for about {length} days each farming year, from {date_range}.",
                         "severity": "context"})

    hits = Counter()
    latest = seasons[-10:]
    for season in latest:
        for event, name in EVENT_NAMES.items():
            daily = season.daily
            flags = getattr(daily, event)
            counts = Counter(zip(daily.crop_id[flags], daily.stage[flags]))
            hits.update((crop_id, stage, name) for (crop_id, stage), count in counts.items()
                        if count >= (3 if name == "heat" else 1))
    if hits:
        (crop_id, stage, event), count = min(hits.items(), key=lambda row: (-row[1], row[0]))
        if count >= 3:
            text = f"{crops[crop_id].name} at {STAGE_NAMES[stage]} faced {event} in {count} of the last {len(latest)} seasons."
            patterns.append({"id": "vulnerable", "text": text, "severity": "caution"})

    significant = [trend for trend in trends if trend["p_value"] < .05 and trend["slope_per_decade"] != 0]
    if significant:
        trend = min(significant, key=lambda row: row["p_value"])
        slope = trend["slope_per_decade"]
        change = "rising" if slope > 0 else "falling"
        start = trend["season_range"][0]
        text = f"{trend['metric'].capitalize()} is {change} since {start}, a statistically clear trend in NASA POWER data ({abs(slope):.1f} {trend['unit']} per decade)."
        patterns.append({"id": "weather_trend", "text": text, "severity": "context"})
    water = grace.get("trend_cm_per_yr")
    if water is not None:
        change = "fallen" if water < 0 else "risen"
        sentence = (f"Water stored on land in this region (~300 km) has {change} about {abs(water):.2f} cm per year since 2002 (GRACE/GRACE-FO)."
                    if abs(water) >= .3 else "GRACE/GRACE-FO shows no strong regional water storage trend.")
        patterns.append({"id": "water_storage", "text": sentence, "severity": "context"})
    return patterns
