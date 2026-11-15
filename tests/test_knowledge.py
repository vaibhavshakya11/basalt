import pytest

from basalt.knowledge.loader import load_assumptions, load_crops, load_punjab_rotations, load_soils
from basalt.soil import soilgrids


def test_knowledge_preserves_specification_values():
    crops = load_crops()
    assert crops["rice_pb"].stage_days == (20, 25, 40, 25)
    assert crops["beans"].stage_fracs == (.18, .27, .36, .18)
    assert crops["wheat_pb"].ranges["kc_ini"] == (.3, .7)
    assert crops["mungbean"].gdd_req == 1100
    assert load_soils()["sandy_loam"].rice_percolation == 8
    assert len(load_punjab_rotations()) == 4
    assert all(entry.confidence == "L" for entry in load_assumptions())


@pytest.mark.parametrize(
    ("fractions", "expected"),
    [
        ((95, 4, 1), "sand"),
        ((84, 10, 6), "loamy_sand"),
        ((69, 20, 11), "sandy_loam"),
        ((40, 40, 20), "loam"),
        ((12, 83, 5), "silt_loam"),
        ((20, 65, 15), "silt_loam"),
        ((55, 15, 30), "clay_loam"),
        ((37, 32, 31), "clay_loam"),
        ((9, 55, 36), "clay_loam"),
        ((47, 10, 43), "clay"),
        ((12, 44, 44), "clay"),
        ((27, 27, 46), "clay"),
    ],
)
def test_usda_texture_to_model_class(fractions, expected):
    assert soilgrids.texture_class(*fractions) == expected


def test_soilgrids_depth_weights_and_reuses_a_completed_cache(monkeypatch, tmp_path):
    sand_by_depth = {"0-5cm": 600, "5-15cm": 700, "15-30cm": 800}
    calls = []

    def fraction(prop, depth, lat, lon):
        calls.append((prop, depth))
        return {
            "sand": sand_by_depth[depth], "silt": 900 - sand_by_depth[depth], "clay": 100,
        }[prop]

    monkeypatch.setattr(soilgrids, "_fetch_fraction", fraction)
    values = soilgrids.fetch_soilgrids(-13.8, 33.45, cache_dir=tmp_path)
    assert len(calls) == 9
    assert values["sand"] == pytest.approx(73.3333)
    assert values["soil_class"] == "sandy_loam"
    assert soilgrids.fetch_soilgrids(-13.8, 33.45, cache_dir=tmp_path) == values
    assert len(calls) == 9
