from collections.abc import Callable

import requests
import streamlit as st

from basalt.config import DEMO_COORDS
from basalt.contracts import Scenario
from basalt.soil.soilgrids import SoilGridsUnavailable
from basalt.ui.components import favicon, goto, header, labels
from basalt.ui.field import field_view
from basalt.ui.howsure import how_sure
from basalt.ui.landing import landing
from basalt.ui.options import options_view


@st.cache_data(show_spinner=False)
def _load_demo(site_id: str) -> dict:
    from basalt.service import load_demo

    return load_demo(site_id)


@st.cache_data(show_spinner=False, max_entries=48)
def _refresh_demo(site_id: str, scenario: Scenario, **setup) -> dict:
    from basalt.service import demo_scenario

    return demo_scenario(site_id, scenario, **setup)


@st.cache_data(show_spinner=False, max_entries=48)
def _analyze(lat: float, lon: float, scenario: Scenario, **setup) -> dict:
    from basalt.service import analyze_location

    return analyze_location(lat, lon, scenario=scenario, **setup)


def _field_session(key: str) -> dict:
    if st.session_state.get("field_key") != key:
        st.session_state["field_key"] = key
        st.session_state["field_model"] = {}
    return st.session_state["field_model"]


def _render_tabs(bundle: dict, key: str, state: dict) -> None:
    ui = labels()
    story = bundle["field_story"]
    heading, navigate = st.columns([.73, .27])
    heading.title(story["site"]["name"])
    if navigate.button(ui["try_other_site"], key="field-home"):
        goto()
    field_tab, options_tab, confidence_tab = st.tabs([ui["tab_field"], ui["tab_options"], ui["tab_sure"]])
    with field_tab:
        updated_field = field_view(bundle, key=key)
    with options_tab:
        new_scenario = options_view(bundle, key=key)
    with confidence_tab:
        how_sure(bundle)
    st.divider()
    st.caption(ui["local_advice"])
    if updated_field is not None:
        soil, irrigated, crop_ids, constraints = updated_field
        state.update(soil_class=soil, irrigated=irrigated, crop_ids=crop_ids, constraints=constraints)
    if new_scenario is not None:
        state["scenario"] = new_scenario
    if updated_field is not None or new_scenario is not None:
        st.rerun()


def _show_field(key: str, load: Callable[..., dict]) -> None:
    ui = labels()
    state = _field_session(key)
    scenario = state.get("scenario", Scenario())
    setup = {name: value for name, value in state.items() if name != "scenario"}
    try:
        with st.spinner(ui["replaying"]):
            bundle = load(scenario, **setup)
    except SoilGridsUnavailable:
        from basalt.knowledge.loader import load_soils

        st.warning(ui["pick_soil"])
        soil = st.selectbox(ui["soil_type"], list(load_soils()), index=None,
                            format_func=lambda value: value.replace("_", " ").capitalize())
        if soil:
            state["soil_class"] = soil
            st.rerun()
        return
    except FileNotFoundError:
        st.error(ui["demo_unavailable"] if key in DEMO_COORDS else ui["fetch_error"])
        return
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        st.error(ui["fetch_error"])
        st.caption(str(exc))
        if setup or scenario != Scenario():
            if st.button(ui["update_field"], key="reset-field"):
                state.clear()
                st.rerun()
        return

    _render_tabs(bundle, key, state)


def run() -> None:
    """Route public field pins and precomputed offline demo views."""
    st.set_page_config(page_title="Basalt", page_icon=favicon(), layout="wide", initial_sidebar_state="collapsed")
    header()
    query = st.query_params
    site_id = query.get("site")
    if site_id in DEMO_COORDS:
        def demo(scenario, **setup):
            if scenario == Scenario() and not setup:
                return _load_demo(site_id)
            return _refresh_demo(site_id, scenario, **setup)

        _show_field(site_id, demo)
    elif "lat" in query or "lon" in query:
        try:
            lat = float(query.get("lat", "nan"))
            lon = float(query.get("lon", "nan"))
        except ValueError:
            lat, lon = float("nan"), float("nan")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            st.error(labels()["invalid_location"])
            if st.button(labels()["try_other_site"]):
                goto()
            return
        _show_field(f"{lat:.5f}_{lon:.5f}", lambda scenario, **setup: _analyze(lat, lon, scenario, **setup))
    else:
        _field_session("landing")
        try:
            preview = _load_demo("ludhiana")
        except FileNotFoundError:
            preview = None
        landing(preview)


if __name__ == "__main__":
    run()
