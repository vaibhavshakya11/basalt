from collections.abc import Sequence

from basalt.contracts import Evidence, Priorities
from basalt.decision.replay import AXES


def order_evidence(evidence: Sequence[Evidence], priorities: Priorities = Priorities()) -> list[Evidence]:
    """Keep the current rotation first and order alternatives by weighted net wins."""
    if any(not 0 <= getattr(priorities, axis) <= 1 for axis in AXES):
        raise ValueError("Priority weights must be between zero and one")

    def score(option: Evidence) -> tuple[bool, float]:
        wins = option["wins_vs_current"]
        weighted_net = sum(getattr(priorities, axis) * (wins[axis]["better"] - wins[axis]["worse"]) for axis in AXES)
        return option["is_current"], weighted_net

    return sorted(evidence, key=score, reverse=True)
