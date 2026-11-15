from basalt.calendar_utils import calendar_windows
from basalt.knowledge.loader import load_crops, load_punjab_rotations
from basalt.satellite.validate import _matched_crop_parameters
from basalt.service import load_demo


def test_matched_parameters_keep_all_calendar_boundaries_across_leap_years():
    local = load_crops()
    generic = _matched_crop_parameters(local)
    for rotation in load_punjab_rotations().values():
        years = range(1999, 2026)
        local_windows = calendar_windows(rotation, local, "06-01", years, minimum_gap=5)
        generic_windows = calendar_windows(rotation, generic, "06-01", years, minimum_gap=5)
        assert [(slot.sow, slot.harvest) for slot in local_windows] == [
            (slot.sow, slot.harvest) for slot in generic_windows
        ]
        assert [sum(slot.stage_days) for slot in local_windows] == [
            sum(slot.stage_days) for slot in generic_windows
        ]
    assert generic["maize_pb"].zr_max_m != local["maize_pb"].zr_max_m


def test_v2_reports_conditional_result_and_excludes_self_comparison_from_second_count():
    result = next(check for check in load_demo("ludhiana")["validation"] if check["check_id"] == "V2")
    assert result["status"] == "caveat"
    assert result["n"] == 12
    assert "Unadjusted GGCMI dates fit 1 of 4 rotations" in result["note"]
    assert result["value"]["Matching alternative arrows"] == result["value"]["Compared alternative arrows"] == 9
