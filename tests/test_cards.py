import json
import re

from basalt.climate.power import load_climate
from basalt.config import DEMO, DEMO_COORDS
from basalt.contracts import Constraints, Site
from basalt.decision.replay import replay
from basalt.explain.cards import build_card
from basalt.knowledge.loader import load_crops, load_punjab_rotations, load_soils


def test_card_numbers_all_come_from_evidence():
    site = Site("ludhiana", *DEMO_COORDS["ludhiana"], "calibrated", "sandy_loam", "demo_default", True, "06-01")
    climate = load_climate(DEMO / "ludhiana" / "climate.parquet")
    rows, _ = replay(
        site, climate, list(load_punjab_rotations().values()), load_crops(), load_soils()[site.soil_class],
        Constraints(irrigations_per_year_max=8, prefer_assured_market=True),
    )
    current = rows[0]
    number = r"-?\d+(?:\.\d+)?"
    for row in rows:
        card = build_card(row, current, irrigated=site.irrigated, calendar_source="pau")
        texts = [row["verdict"], *(line for section in card.values() for line in section)]
        from_evidence = [float(value) for value in re.findall(number, json.dumps([row, current]))]
        for value in map(float, re.findall(number, " ".join(texts))):
            assert any(abs(value - source) <= max(0.5, abs(source) * 0.01) for source in from_evidence), (row["rotation_id"], value)
        assert card["risks"][-1].startswith("Check this with your local agriculture office")
