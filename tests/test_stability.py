from dataclasses import replace

from basalt.contracts import CropSlot, ModelParameters, Rotation, RotationRun, Site
from basalt.decision.stability import stability
from basalt.knowledge.loader import load_crops, load_soils
from test_replay import season_row


def test_stability_names_the_parameter_that_changes_an_arrow(monkeypatch):
    rice = CropSlot("rice_pb", "06-20")
    wheat = CropSlot("wheat_pb", "11-01")
    rotations = (
        Rotation("r", "Rice", "current", 1, ((rice,),), True, ""),
        Rotation("rw", "Rice and wheat", "fill_the_gap", 1, ((rice, wheat),), False, ""),
    )
    site = Site("site", "Local field", 30, 75, "calibrated", "loam", "user", True, "06-01")
    seasons = tuple(season_row(year) for year in range(2001, 2025))
    baseline = {rotation.rotation_id: RotationRun(rotation, seasons, ()) for rotation in rotations}
    percolation_tested = []

    def rerun(*args, parameters=ModelParameters(), **kwargs):
        if parameters.rice_percolation is not None:
            percolation_tested.append(parameters.rice_percolation)
        if parameters.rice_percolation == 15:
            option = replace(baseline["rw"], seasons=tuple(replace(season, et_mm=50) for season in seasons))
            return {**baseline, "rw": option}
        return baseline

    monkeypatch.setattr("basalt.decision.stability.replay_runs", rerun)
    soils = load_soils()
    badge = stability(site, None, rotations, load_crops(), soils["loam"], soils, baseline=baseline)
    assert percolation_tested == [2, 15]
    assert badge["r"] == {"badge": "robust", "drivers": []}
    assert badge["rw"] == {
        "badge": "depends",
        "drivers": [{"param": "rice_percolation", "label": "rice field water loss into the ground"}],
    }
