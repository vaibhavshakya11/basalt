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
    assert not app.exception
    assert not app.error
    assert any("Scenario: +2 °C, -10% rain" in paragraph.value for paragraph in app.markdown)
