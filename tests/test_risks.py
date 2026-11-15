import numpy as np
import pytest

from basalt.physics.risks import burn_pressure, erosion


def test_erosion_marks_bare_events_even_under_retained_residue():
    rain = np.array([12.6, 12.7, 20., 20.])
    impact, event = erosion(rain, np.array(["bare", "bare", "bare", "mid"]),
                            np.array([False, False, True, False]))
    assert event.tolist() == [False, True, True, False]
    assert impact.tolist() == pytest.approx([0, 12.7**1.81, .4 * 20**1.81, .1 * 20**1.81])


def test_burn_pressure_tracks_gap_and_machinery():
    assert burn_pressure("high", 21, False) == 1.
    assert burn_pressure("medium", 22, True) == .075
    assert burn_pressure("high", 42, False) == .15
