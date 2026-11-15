import urllib.request

import pytest
import requests
from streamlit.testing.v1 import AppTest

from basalt.config import ROOT


@pytest.fixture
def network_off(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Demo made a network request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def test_landing_has_public_offline_demo_buttons(network_off):
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=12)
    assert not app.exception
    assert [button.label for button in app.button][:2] == ["Try Ludhiana, India", "Try central Malawi"]
    assert len(app.get("plotly_chart")) == 1


@pytest.mark.parametrize("site", ("ludhiana", "malawi"))
def test_each_demo_has_three_tabs_and_needs_no_network(site, network_off):
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.query_params["site"] = site
    app.run(timeout=12)
    assert not app.exception
    assert not app.error
    assert [tab.label for tab in app.tabs] == ["Your field", "Your options", "How sure are we?"]
    assert len(app.get("plotly_chart")) > 1
    assert any("Validation checks" in paragraph.value for paragraph in app.markdown)


def test_demo_scenario_replays_archived_weather_without_network(network_off, monkeypatch):
    events = []
    monkeypatch.setattr("basalt.ui.options.scenario_picker", lambda *args, **kwargs: events[-1] if events else None)
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.query_params["site"] = "ludhiana"
    app.run(timeout=12)
    assert not any("Scenario: +2 °C, -10% rain" in paragraph.value for paragraph in app.markdown)

    events.append({"receipt": "app-test-1", "temperature": 2, "rainfall": -10})
    app.run(timeout=12)
    assert not app.exception
    assert not app.error
    assert any("Scenario: +2 °C, -10% rain" in paragraph.value for paragraph in app.markdown)

    events.append({"receipt": "app-test-2", "temperature": 0, "rainfall": 0})
    app.run(timeout=12)
    assert not app.exception
    assert not any("Scenario: +2 °C, -10% rain" in paragraph.value for paragraph in app.markdown)


def test_invalid_location_link_leaves_demos_reachable(network_off):
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.query_params["lat"] = "NaN"
    app.query_params["lon"] = "75.7"
    app.run(timeout=12)
    assert not app.exception
    assert "Choose a latitude" in app.warning[0].value
    assert any(button.label == "Try Ludhiana, India" for button in app.button)


def test_uncovered_pin_explains_next_action_without_querying_weather(network_off, monkeypatch):
    monkeypatch.setattr("basalt.service.local_calendars", lambda *args, **kwargs: ())
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.query_params["lat"] = "-70"
    app.query_params["lon"] = "-100"
    app.run(timeout=12)
    assert not app.exception
    assert "No supported crop calendar" in app.error[0].value
    assert any(button.label == "Open the demos" for button in app.button)


def test_overlapping_crop_update_preserves_current_replay(network_off):
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.query_params["site"] = "malawi"
    app.run(timeout=12)
    crops = next(widget for widget in app.multiselect if widget.label == "Current crops")
    crops.set_value(["maize", "groundnut"]).run(timeout=12)
    next(button for button in app.button if button.label == "Update field").click().run(timeout=12)
    assert not app.exception
    assert any("previous replay is still shown" in item.value for item in app.warning)
    assert any(item.label == "Your options" for item in app.tabs)



def test_weather_failure_can_retry_the_same_location(network_off, monkeypatch):
    from basalt.climate.power import PowerError
    from basalt.service import load_demo

    attempts = []

    def analyze(lat, lon, **setup):
        attempts.append((lat, lon))
        if len(attempts) == 1:
            raise PowerError("upstream temporarily unavailable")
        return load_demo("ludhiana")

    monkeypatch.setattr("basalt.service.analyze_location", analyze)
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.query_params["lat"], app.query_params["lon"] = "30.79", "75.71"
    app.run(timeout=12)
    assert "NASA POWER weather is temporarily unavailable" in app.error[0].value
    next(button for button in app.button if button.label == "Try again").click().run(timeout=12)
    assert not app.exception
    assert not app.error
    assert attempts == [(30.79, 75.71), (30.79, 75.71)]
    assert any(tab.label == "Your field" for tab in app.tabs)


def test_unavailable_soil_can_be_entered_without_losing_the_pin(network_off, monkeypatch):
    from basalt.service import load_demo
    from basalt.soil.soilgrids import SoilGridsUnavailable

    attempts = []

    def analyze(lat, lon, **setup):
        soil = setup.get("soil_class")
        attempts.append((lat, lon, soil))
        if soil is None:
            raise SoilGridsUnavailable("upstream temporarily unavailable")
        return load_demo("ludhiana")

    monkeypatch.setattr("basalt.service.analyze_location", analyze)
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.query_params["lat"], app.query_params["lon"] = "30.89", "75.81"
    app.run(timeout=12)
    assert "soil data service" in app.warning[0].value
    app.selectbox[0].set_value("loam").run(timeout=12)
    next(button for button in app.button if button.label == "Use this soil").click().run(timeout=12)
    assert not app.exception
    assert not app.error
    assert attempts[-1] == (30.89, 75.81, "loam")
    assert all((lat, lon) == (30.89, 75.81) for lat, lon, _ in attempts)
