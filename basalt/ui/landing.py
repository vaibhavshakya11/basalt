from html import escape

import streamlit as st

from basalt.config import SCOPE, SLIDES_URL
from basalt.ui.components import goto, how_it_works, labels, stage_navigation
from basalt.ui.map import map_view
from basalt.ui.strata import draw_strata_legend, strata_figure


def _location_picker() -> None:
    ui = labels()
    with st.container(key="landing-location"):
        with st.expander(ui["choose_location"]):
            st.caption(ui["location_help"])
            st.session_state.setdefault("field_lat", 30.8)
            st.session_state.setdefault("field_lon", 75.7)
            picked = map_view(st.session_state["field_lat"], st.session_state["field_lon"], key="location-picker")
            if picked and picked != st.session_state.get("last_map_pin"):
                st.session_state["field_lat"] = picked["lat"]
                st.session_state["field_lon"] = picked["lon"]
                st.session_state["last_map_pin"] = picked
            with st.form("location-form", border=False):
                lat, lon = st.columns(2)
                latitude = lat.number_input(ui["latitude"], min_value=-90., max_value=90., value=None,
                                            step=.01, format="%.5f", key="field_lat")
                longitude = lon.number_input(ui["longitude"], min_value=-180., max_value=180., value=None,
                                             step=.01, format="%.5f", key="field_lon")
                if st.form_submit_button(ui["use_location"]):
                    if latitude is None or longitude is None:
                        st.error(ui["location_missing"])
                    else:
                        goto(lat=latitude, lon=longitude)


def _intro() -> None:
    ui = labels()
    with st.container(key="landing-lead"):
        st.markdown(
            f'<div class="b-hero"><h1>{escape(ui["page_title"])}</h1><p>{escape(ui["page_intro"])}</p></div>',
            unsafe_allow_html=True,
        )
        with st.container(key="landing-demos"):
            ludhiana, malawi = st.columns(2, gap="small")
            ludhiana.button(ui["demo_india"], type="primary", use_container_width=True,
                            on_click=stage_navigation, kwargs={"site": "ludhiana"})
            malawi.button(ui["demo_malawi"], use_container_width=True,
                          on_click=stage_navigation, kwargs={"site": "malawi"})
        _location_picker()


def _preview(bundle: dict | None) -> None:
    ui = labels()
    with st.container(key="landing-preview"):
        if not bundle:
            st.caption(ui["demo_unavailable"])
            return
        story = bundle["field_story"]
        current = story["current_rotation_id"]
        site = escape(story["site"]["name"])
        season_range = next(option["season_range"] for option in bundle["evidence"] if option["rotation_id"] == current)
        period = f"{season_range[0]}–{season_range[1]}"
        st.markdown(
            f'<div class="b-preview-heading"><div><h2>{escape(ui["strata"])}</h2>'
            f'<p>{site}</p></div><span class="b-preview-period">{period}</span></div>',
            unsafe_allow_html=True,
        )
        strata = bundle["strata"][current]
        chart = strata_figure(strata)
        chart.update_xaxes(tickangle=0, tickfont_size=10)
        st.plotly_chart(chart, use_container_width=True, theme=None, key="landing-strata",
                        config={"displayModeBar": False, "scrollZoom": False})
        draw_strata_legend([strata])


def _supporting_information() -> None:
    ui = labels()
    with st.container(key="landing-support"):
        source, actions = st.columns([.58, .42], gap="large")
        with source:
            st.caption(ui["data_caption"])
            st.caption(SCOPE)
            st.caption(ui["local_advice"])
        with actions, st.container(key="landing-method"):
            method, presentation = st.columns([2.7, 1], gap="small")
            with method:
                how_it_works()
            with presentation:
                if SLIDES_URL == "?view=slides":
                    st.button(ui["slides"], use_container_width=True,
                              on_click=stage_navigation, kwargs={"view": "slides"})
                elif SLIDES_URL.startswith("https://"):
                    st.link_button(ui["slides"], SLIDES_URL, use_container_width=True)
                else:
                    st.button(ui["slides"], disabled=True, help=ui["slides_unavailable"], use_container_width=True)


def landing(bundle: dict | None) -> None:
    """Show the demo entry points and their precomputed field preview."""
    with st.container(key="landing"):
        with st.container(key="landing-grid"):
            intro, figure = st.columns([.43, .57], gap="large")
            with intro:
                _intro()
            with figure:
                _preview(bundle)
        _supporting_information()
