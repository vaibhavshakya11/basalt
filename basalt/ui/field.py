from html import escape

import streamlit as st

from basalt.contracts import Constraints
from basalt.ui.components import APP_COLOR, labels
from basalt.ui.map import map_view
from basalt.ui.strata import draw_strata


def field_inputs(bundle: dict, *, key: str) -> tuple[str, bool, tuple[str, ...], Constraints] | None:
    """Let the grower correct the model's field assumptions."""
    ui = labels()
    setup = bundle["setup"]
    soil = setup["soil_class"]
    soils = setup["soil_classes"]
    crop_options = setup["crop_options"]
    crop_ids = setup["current_crop_ids"]
    calibrated = bundle["field_story"]["tier"] == "calibrated"
    with st.form(f"field-{key}", border=True):
        soil_col, crop_col = st.columns(2)
        soil_type = soil_col.selectbox(ui["soil_type"], soils, index=soils.index(soil) if soil in soils else None,
                                       format_func=lambda value: value.replace("_", " ").capitalize())
        if calibrated:
            chosen = crop_col.selectbox(ui["crops"], list(crop_options),
                                        index=list(crop_options).index(crop_ids[0]) if crop_ids else None,
                                        format_func=crop_options.__getitem__)
            chosen_ids = (chosen,) if chosen else ()
        else:
            chosen_ids = tuple(crop_col.multiselect(ui["crops"], list(crop_options), default=crop_ids,
                                                   format_func=crop_options.__getitem__))
        irrigated = st.toggle(ui["irrigated"], value=setup["irrigated"])
        with st.expander(ui["my_limits"]):
            known = st.checkbox(ui["limit_known"], value=setup.get("irrigations_per_year_max") is not None)
            limit = st.number_input(ui["irrigations_max"], min_value=0, step=1,
                                    value=setup.get("irrigations_per_year_max") or 0)
            has_machinery = st.checkbox(ui["residue_machinery"], value=setup.get("has_residue_machinery", False))
            assured = calibrated and st.checkbox(ui["assured_market"], value=setup.get("prefer_assured_market", False))
        if st.form_submit_button(ui["update_field"]) and soil_type is not None and chosen_ids:
            return soil_type, irrigated, chosen_ids, Constraints(limit if known else None, has_machinery, assured)
    return None


def _regional_water(story: dict, key: str) -> None:
    ui = labels()
    st.subheader(ui["storage"])
    place = story["site"]
    grace = story.get("grace") or {}
    slope = grace.get("trend_cm_per_yr")
    map_view(place["lat"], place["lon"], fixed=True, key=f"storage-{key}", trend=slope)
    st.caption(ui["storage_caption"])
    if slope is None:
        st.caption(ui["storage_none"])
    else:
        tone = APP_COLOR["iron"] if slope < 0 else "#3D7FC4"
        sign = ui["storage_drier"] if slope < 0 else ui["storage_wetter"]
        text = f'{sign} {abs(slope):.2f} {ui["storage_unit"]}'
        st.markdown(f'<span style="color:{tone}">{escape(text)}</span>', unsafe_allow_html=True)
        if grace.get("period"):
            st.caption(grace["period"])


def field_view(bundle: dict, *, key: str) -> tuple[str, bool, tuple[str, ...], Constraints] | None:
    """Show the archived and current calendar for this field."""
    ui = labels()
    story = bundle["field_story"]
    st.subheader(ui["field_header"])
    updated = field_inputs(bundle, key=key)
    st.caption(ui[story["tier"]])
    st.subheader(ui["strata"])
    st.caption(ui["older_lower"])
    draw_strata(bundle["strata"][story["current_rotation_id"]], key=f"current-strata-{key}")
    st.divider()
    notes, region = st.columns([.52, .48], gap="large")
    with notes:
        if story.get("patterns"):
            st.subheader(ui["patterns"])
            for pattern in story["patterns"]:
                st.markdown(f'<div class="b-pattern">{escape(pattern["text"])}</div>', unsafe_allow_html=True)
        st.subheader(ui["calendar"])
        st.write(ui["calendar_source"][story["calendar_source"]])
        if story["ndvi_seasons_detected"]:
            st.caption(ui["ndvi_detected"].format(n=story["ndvi_seasons_detected"]))
    with region:
        _regional_water(story, key)
    return updated
