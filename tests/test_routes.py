import pytest

from basalt.routes import parse_route


@pytest.mark.parametrize("query", [
    {"site": ["ludhiana", "malawi"]},
    {"site": ["ludhiana"], "lat": ["30.8"], "lon": ["75.7"]},
    {"view": ["slides"], "site": ["malawi"]},
    {"view": ["missing"]},
    {"lat": ["30.8"]},
    {"lat": ["-91"], "lon": ["75.7"]},
    {"lat": ["30.8"], "lon": ["181"]},
    {"lat": ["30.8"], "lon": ["inf"]},
    {"lat": ["nan"], "lon": ["75.7"]},
    {"lat": ["30.8"], "lon": ["east"]},
])
def test_malformed_links_cannot_start_a_replay(query):
    assert parse_route(query).kind == "invalid"


def test_valid_public_routes_ignore_nonrouting_parameters():
    assert parse_route({"view": ["slides"], "utm_source": ["team"]}).kind == "slides"
    assert parse_route({"site": ["MaLaWi"], "embed": ["true"]}).site == "malawi"
    pin = parse_route({"lat": ["-0"], "lon": ["180"]})
    assert pin.coordinates == (0., -180.)
    assert parse_route({}).kind == "landing"
