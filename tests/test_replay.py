from dataclasses import replace
from pathlib import Path

import pytest

from basalt.climate.power import load_climate
from basalt.config import DEMO
from basalt.contracts import CropSlot, Rotation, SeasonResult, Site
from basalt.decision.replay import arrows_for, erosion_reference, paired_wins, replay
from basalt.knowledge.loader import load_crops, load_soils
from basalt.physics.soilhealth import FACTORS


def season_row(year):
    return SeasonResult(
        season=year, et_mm=100, irr_net_mm=0, irr_gross_mm=0, irr_events=0, rain_mm=0,
        runoff_mm=0, deep_perc_mm=0, heat_days=0, heat_hit_crops=0, frost_days=0,
        frost_hit_crops=0, dry_stress_frac=0.3, dry_hit_crops=0, risk_hits=2,
        bare_days=0, erosion_index=0, burn_pressure=0, soil_factors=dict.fromkeys(FACTORS, 0),
        soil_score=50, wb_residual_max_mm=0, irr_exceeds_limit=False,
    )


@pytest.mark.parametrize("irrigated", [False, True])
def test_replay_counts_exact_thresholds_and_arrows(irrigated):
    current = [season_row(year) for year in range(2001, 2025)]
    better = [replace(row, soil_score=52, et_mm=97, dry_stress_frac=0.25, risk_hits=1) for row in current[:16]]
    worse = [replace(row, soil_score=48, et_mm=103, dry_stress_frac=0.35, risk_hits=3) for row in current[16:21]]
    similar = [replace(row, soil_score=51.9, et_mm=102.9, dry_stress_frac=0.26) for row in current[21:]]
    wins = paired_wins(current, better + worse + similar, irrigated)
    for axis in wins:
        assert wins[axis] == {"better": 16, "worse": 5, "tie": 3}
        assert arrows_for(wins)[axis] == "better"
        assert arrows_for(wins, 18)[axis] == "similar"


def test_two_year_alternative_stores_both_phases_and_compares_shared_erosion_reference():
    weather = load_climate(Path(DEMO) / "malawi" / "climate.parquet")
    site = Site("malawi", "Malawi", -13.8, 33.45, "global", "clay_loam", "user", False, "09-01")
    maize = CropSlot("maize", "11-15", "03-20")
    beans = CropSlot("beans", "11-15", "02-27")
    rotations = (
        Rotation("m", "Maize", "current", 1, ((maize,),), True, ""),
        Rotation("mb", "Maize and beans", "take_turns", 2, ((maize,), (beans,)), False, ""),
    )
    _, runs = replay(site, weather, rotations, load_crops(), load_soils()["clay_loam"])
    ref = erosion_reference(runs["m"])
    paired = runs["mb"]
    assert len(paired.phases) == 2
    assert all(len(phase) == 24 for phase in paired.phases)
    first, second = (phase[0] for phase in paired.phases)
    assert "maize" in set(first.daily.crop_id) and "beans" in set(second.daily.crop_id)
    assert paired.seasons[0].et_mm == pytest.approx((first.result.et_mm + second.result.et_mm) / 2)
    for phase in paired.phases:
        for season in phase:
            assert season.result.soil_factors["erosive_rain_bare"] == pytest.approx(
                1 - min(1, season.result.erosion_index / ref),
            )
