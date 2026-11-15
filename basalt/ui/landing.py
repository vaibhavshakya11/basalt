from html import escape

import streamlit as st

from basalt.config import SCOPE, SLIDES_URL
from basalt.ui.components import goto, how_it_works, labels
from basalt.ui.map import map_view
from basalt.ui.strata import draw_strata


def _location_picker() -> None:
    ui = labels()
    with st.expander(ui["choose_location"], expanded=False):
        st.caption(ui["location_help"])
        st.session_state.setdefault("field_lat", 30.8)
        st.session_state.setdefault("field_lon", 75.7)
        picked = map_view(st.session_state["field_lat"], st.session_state["field_lon"], key="location-picker")
        if picked and picked != st.session_state.get("last_map_pin"):
            st.session_state["field_lat"] = picked["lat"]
            st.session_state["field_lon"] = picked["lon"]
            st.session_state["last_map_pin"] = picked
        with st.form("location-form"):
            lat, lon = st.columns(2)
            latitude = lat.number_input(ui["latitude"], min_value=-90., max_value=90., value=None,
                                        step=.01, format="%.5f", key="field_lat")
            longitude = lon.number_input(ui["longitude"], min_value=-180., max_value=180., value=None,
                                         step=.01, format="%.5f", key="field_lon")
            if st.form_submit_button(ui["use_location"]):
                goto(lat=latitude, lon=longitude)


def landing(bundle: dict | None) -> None:
    """Render the demo entry points and a real Ludhiana Season Strata."""
    ui = labels()
    intro, season_strata = st.columns([.45, .55], gap="large")
    with intro:
        st.markdown('<div class="b-hero">'
                    f'<h1>{escape(ui["page_title"])}</h1><p>{escape(ui["page_intro"])}</p></div>',
                    unsafe_allow_html=True)
        if st.button(ui["demo_india"], type="primary"):
            goto(site="ludhiana")
        if st.button(ui["demo_malawi"]):
            goto(site="malawi")
        if SLIDES_URL == "?view=slides":
            if st.button(ui["slides"]):
                goto(view="slides")
        elif SLIDES_URL.startswith("https://"):
            st.link_button(ui["slides"], SLIDES_URL)
        else:
            st.button(ui["slides"], disabled=True, help=ui["slides_unavailable"])
        how_it_works()
        _location_picker()
        st.caption(ui["data_caption"])
    with season_strata:
        if bundle:
            current = bundle["field_story"]["current_rotation_id"]
            draw_strata(bundle["strata"][current], key="landing-strata")
            st.caption(ui["hero_caption"])
        else:
            st.caption(ui["demo_unavailable"])
    st.divider()
    st.caption(SCOPE)
    st.caption(ui["local_advice"])
