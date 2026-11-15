import pytest

from basalt.contracts import Scenario
from basalt.ui.options import _scenario_from_event


def test_scenario_event_applies_both_values():
    assert _scenario_from_event({"temperature": 2, "rainfall": -10}) == Scenario(2, 0.9)
    assert _scenario_from_event({"temperature": 0, "rainfall": 0}) == Scenario()


@pytest.mark.parametrize(
    "event",
    [
        None,
        {"temperature": 2},
        {"temperature": 2.1, "rainfall": 0},
        {"temperature": 3.5, "rainfall": 0},
        {"temperature": 3, "rainfall": 35},
        {"temperature": 3, "rainfall": -2},
        {"temperature": True, "rainfall": 0},
    ],
)
def test_scenario_event_rejects_values_outside_either_slider(event):
    assert _scenario_from_event(event) is None
