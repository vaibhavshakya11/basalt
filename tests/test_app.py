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


def test_demo_sliders_replay_archived_weather_without_network(network_off):
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.query_params["site"] = "ludhiana"
    app.run(timeout=12)
    app.slider(key="temperature-ludhiana").set_value(2.0).run(timeout=12)
    app.slider(key="rainfall-ludhiana").set_value(-10).run(timeout=12)
    assert not any("Scenario: +2 °C, -10% rain" in paragraph.value for paragraph in app.markdown)
    next(button for button in app.button if button.label == "Apply scenario").click().run(timeout=12)
    assert not app.exception
    assert not app.error
    assert any("Scenario: +2 °C, -10% rain" in paragraph.value for paragraph in app.markdown)



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
