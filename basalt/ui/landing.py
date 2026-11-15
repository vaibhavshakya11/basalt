from html import escape

import streamlit as st

from basalt.config import DEMO_PROFILES, SLIDES_URL, YEARS
from basalt.ui.components import goto, labels, stage_navigation
from basalt.ui.map import map_view
from basalt.ui.strata import EVENTS, draw_strata_legend, strata_figure

LEAD_DEMOS = ("ludhiana", "malawi")
PREVIEW_YEARS = len(YEARS)


def _location_picker() -> None:
    ui = labels()
    with st.container(key="landing-location"):
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


def _toggle_location() -> None:
    st.session_state["landing_location_open"] = not st.session_state.get("landing_location_open", False)


def _intro() -> None:
    ui = labels()
    with st.container(key="landing-lead"):
        st.markdown(
            '<div class="b-home-intro"><p class="b-home-eyebrow">NASA Space Apps 2026 · Field Shift</p>'
            f'<h1>{escape(ui["page_title"])}</h1><p class="b-home-lead">{escape(ui["page_intro"])}</p></div>',
            unsafe_allow_html=True,
        )
        st.button(ui["demo_india"], type="primary", on_click=stage_navigation, kwargs={"site": "ludhiana"})
        with st.container(key="landing-links"):
            malawi, location, directory = st.columns(3, gap="small")
            malawi.button(ui["demo_malawi"], on_click=stage_navigation, kwargs={"site": "malawi"})
            location.button("Choose your own location", on_click=_toggle_location)
            directory.button("Other demo fields", on_click=stage_navigation, kwargs={"view": "demo-fields"})
        if st.session_state.get("landing_location_open", False):
            _location_picker()


def _preview(bundle: dict | None) -> None:
    with st.container(key="landing-preview"):
        if not bundle:
            st.caption(labels()["demo_unavailable"])
            return
        current = bundle["field_story"]["current_rotation_id"]
        strata = bundle["strata"][current]
        events = tuple(event for event in EVENTS if any(row["events"].get(event) for row in strata["rows"]))
        chart = strata_figure(strata, events=events)
        chart.update_layout(height=355, margin={"l": 50, "r": 3, "t": 4, "b": 22})
        chart.update_xaxes(title_text=None, tickangle=0, tickfont_size=10)
        chart.update_yaxes(title_text=None, tickfont={"family": "IBM Plex Mono, monospace", "size": 9})
        st.plotly_chart(chart, use_container_width=True, theme=None, key="landing-strata",
                        config={"displayModeBar": False, "scrollZoom": False})
        st.caption("Ludhiana, 2001 to 2024. Each row is one farming year. Sand colour is bare soil.")
        draw_strata_legend([strata], events=events)


def _supporting_information() -> None:
    ui = labels()
    with st.container(key="landing-method"):
        st.header(ui["how_it_works"])
        st.markdown(
            '<ol class="b-home-steps">'
            "<li>Read your field's calendar from NASA satellites.</li>"
            '<li>Replay each rotation through 24 real seasons of NASA weather.</li>'
            '<li>Compare season by season with what you grow now.</li></ol>',
            unsafe_allow_html=True,
        )
        st.caption(ui["data_caption"])
        if SLIDES_URL == "?view=slides":
            st.button(ui["slides"], on_click=stage_navigation, kwargs={"view": "slides"})
        elif SLIDES_URL.startswith("https://"):
            st.markdown(f'<a class="b-text-link" href="{escape(SLIDES_URL)}">{escape(ui["slides"])}</a>',
                        unsafe_allow_html=True)


def landing(bundle: dict | None) -> None:
    """Show the primary replay entry point and the full Ludhiana record."""
    with st.container(key="landing"):
        with st.container(key="landing-grid"):
            intro, figure = st.columns([5, 7], gap="large", vertical_alignment="center")
            with intro:
                _intro()
            with figure:
                _preview(bundle)
        _supporting_information()


def directory_page() -> None:
    """List the other fields without competing with the homepage entry point."""
    ui = labels()
    with st.container(key="landing-directory"):
        st.title("Other demo fields")
        st.markdown(ui["demos_intro"])
        rows = []
        for site, profile in DEMO_PROFILES.items():
            if site not in LEAD_DEMOS:
                rows.append(
                    f'<li><a class="b-text-link" href="?site={escape(site)}">{escape(profile["label"])}</a>'
                    f'<p>{escape(profile["summary"])}</p></li>'
                )
        st.html(f'<ul class="b-home-directory">{"".join(rows)}</ul>')
        st.html('<a class="b-text-link" href="?">Back to basalt</a>')
