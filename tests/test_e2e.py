import json

from pydantic import TypeAdapter

from basalt.config import DEMO, DEMO_COORDS, DEMO_PROFILES
from basalt.contracts import Evidence, Scenario
from basalt.service import demo_scenario, load_demo


def test_ludhiana_expected_pumping_and_soil_practices():
    bundle = load_demo("ludhiana")
    by_id = {row["rotation_id"]: row for row in bundle["evidence"]}
    rice = by_id["pb_rw"]["metrics"]
    maize = by_id["pb_mw"]["metrics"]
    assert rice["irr_gross_mm"]["median"] > maize["irr_gross_mm"]["median"]
    assert rice["soil_factors"]["no_puddling"]["median"] == 0
    assert all(row["n_seasons"] == 24 for row in bundle["evidence"])


def test_committed_demo_evidence_matches_contract():
    adapter = TypeAdapter(list[Evidence])
    for site in DEMO_COORDS:
        bundle = json.loads((DEMO / site / "bundle.json").read_text())
        rows = adapter.validate_python(bundle["evidence"])
        for row in rows:
            assert row["site_id"] == site
            assert all(sum(count.values()) == row["n_seasons"] for count in row["wins_vs_current"].values())


def test_demo_scenario_works_offline_and_changes_water(monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("A demo path tried to access the network")

    monkeypatch.setattr("requests.sessions.Session.request", deny_network)
    baseline = load_demo("ludhiana")
    altered = demo_scenario("ludhiana", Scenario(2, .9))
    assert altered["evidence"][0]["metrics"]["et_mm"]["median"] != baseline["evidence"][0]["metrics"]["et_mm"]["median"]
    assert [row["stability"] for row in altered["evidence"]] == [row["stability"] for row in baseline["evidence"]]



def test_demo_profiles_match_their_committed_replays():
    assert len(DEMO_COORDS) == 8 and "jaipur" in DEMO_PROFILES
    for site_id, (site_name, lat, lon) in DEMO_COORDS.items():
        profile, bundle = DEMO_PROFILES[site_id], load_demo(site_id)
        site = bundle["field_story"]["site"]
        assert (site["name"], site["lat"], site["lon"]) == (site_name, lat, lon)
        assert bundle["setup"]["current_crop_ids"] == list(profile["crop_ids"])
        assert bundle["setup"]["irrigated"] == profile["irrigated"]
        assert all(row["n_seasons"] == 24 for row in bundle["evidence"])
