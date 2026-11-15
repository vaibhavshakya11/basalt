from itertools import groupby

from basalt.contracts import Crop, RotationRun

EVENTS = {"heat": "heat_event", "frost": "frost_event", "rain": "erosive_bare_event", "dry": "dry_stress_event"}


def _row(season, crops: dict[str, Crop]) -> dict:
    day_states = zip(season.daily.crop_id, season.daily.stage)
    segments = []
    start = 1
    for (crop_id, stage), group in groupby(day_states):
        end = start + sum(1 for _ in group) - 1
        crop = crops.get(crop_id)
        segments.append([start, end, crop.name if crop else "Bare soil", crop.family if crop else "bare", stage])
        start = end + 1
    return {
        "season": season.season, "segments": segments,
        "events": {label: [int(day)+1 for day in getattr(season.daily, field).nonzero()[0]]
                   for label, field in EVENTS.items()},
    }


def encode_strata(run: RotationRun, crops: dict[str, Crop], season_year_start: str) -> dict:
    """Encode contiguous day segments and event positions for the Strata chart."""
    return {"season_year_start": season_year_start,
            "rows": [_row(season, crops) for season in run.phases[0]],
            "alternate_rows": [_row(season, crops) for season in run.phases[1]] if len(run.phases) > 1 else []}
