from html import escape

import streamlit as st

from basalt.contracts import Constraints
from basalt.ui.components import APP_COLOR, labels
from basalt.ui.map import map_view
from basalt.ui.strata import EVENTS, draw_strata, draw_strata_legend, farming_year_label

FIELD_STYLE = """
<style>
.stApp .st-key-field-summary{padding:8px 0 20px}
.stApp .b-field-facts{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px 24px;
 border-top:1px solid var(--fracture);margin:4px 0 0;padding:12px 0;min-width:0}
.stApp .b-field-fact:first-child{grid-column:1/-1}
.stApp .b-field-fact dt{color:var(--ash);font-size:13px;margin:0 0 2px}
.stApp .b-field-fact dd{margin:0;font-size:16px;font-weight:600;line-height:1.3;overflow-wrap:anywhere}
.stApp .b-field-fact:first-child dd{font-size:19px}
.stApp .b-field-reading{padding:4px 0;border-inline-start:4px solid var(--iron);padding-inline-start:24px}
.stApp .b-field-reading h2{font-weight:600;font-size:17px;margin:0;padding:0}
.stApp .b-field-reading-value{display:block;color:var(--basalt);font-size:clamp(38px,5vw,66px);font-weight:650;
 font-variant-numeric:tabular-nums;line-height:1.12;margin:3px 0 10px}
.stApp .b-field-reading-value span{font-size:.46em}
.stApp .b-field-reading p,.stApp .b-field-strata-title p{margin:0;color:var(--ash);max-width:62ch}
.stApp .st-key-field-chart{padding:24px;background:var(--plate);border:1px solid var(--fracture);border-radius:4px}
.stApp .b-field-strata-title h2{font-size:24px;margin:0;padding:0 0 5px}
.stApp .b-field-strata-title p{font-size:15px}
.stApp .st-key-field-chart .b-strata-legend section{border:0}
.stApp .st-key-field-chart [data-testid="stPlotlyChart"]{max-width:100%;overflow-x:clip}
.stApp .st-key-field-notes{padding-top:20px}
.stApp .st-key-field-notes h3{font-size:20px;margin:0;padding:0 0 6px}
.stApp .b-field-pattern-list{list-style:none;margin:0;padding:0}
.stApp .b-field-pattern-list li{border-top:1px solid var(--fracture);padding:10px 0;line-height:1.45}
.stApp .b-field-pattern-list li:first-child{border-top:0;padding-top:0}
.stApp .b-field-water-reading{margin:0 0 2px;font-size:17px;font-weight:600}
.stApp .b-field-water-reading strong{font-family:'IBM Plex Mono',monospace;font-weight:400}
@media(max-width:700px){
 .stApp .st-key-field-summary{padding:0 0 10px}
 .stApp .b-field-reading{padding-inline-start:14px}
 .stApp .st-key-field-chart{padding:14px 12px}
 .stApp .b-field-facts{grid-template-columns:1fr 1fr;gap:8px 12px}
 .stApp .b-field-strata-title h2{font-size:22px}
 .st-key-field-chart g.xtick:nth-child(even){display:none}
}
</style>
"""


def _soil_name(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _field_facts(setup: dict) -> None:
    ui = labels()
    mode = "irrigated" if setup["irrigated"] else "rainfed"
    crops = [setup["crop_options"].get(crop_id, _soil_name(crop_id)) for crop_id in setup["current_crop_ids"]]
    facts = (
        (ui["crops"], ", ".join(crops) or ui["field_unknown"]),
        (ui["soil_type"], _soil_name(setup["soil_class"]) if setup["soil_class"] else ui["field_unknown"]),
        (ui["field_water_mode"], ui["field_modes"][mode]),
    )
    markup = "".join(
        f'<div class="b-field-fact"><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>'
        for label, value in facts
    )
    st.markdown(f'<dl class="b-field-facts">{markup}</dl>', unsafe_allow_html=True)


def field_inputs(
    bundle: dict, *, key: str, editor_open: bool = False,
) -> tuple[str, bool, tuple[str, ...], Constraints] | None:
    """Edit field assumptions, choosing crops available for the draft water source."""
    ui = labels()
    setup = bundle["setup"]
    soils = setup["soil_classes"]
    soil = setup["soil_class"]
    crop_ids = setup["current_crop_ids"]
    calibrated = bundle["field_story"]["tier"] == "calibrated"
    current_mode = "irrigated" if setup["irrigated"] else "rainfed"
    with st.expander(ui["field_edit"], expanded=editor_open):
        mode = st.radio(
            ui["field_water_mode"], ("irrigated", "rainfed"), index=int(not setup["irrigated"]),
            format_func=ui["field_modes"].__getitem__, horizontal=True, key=f"field-water-{key}",
        )
        crop_options = setup.get("crop_options_by_water", {}).get(mode)
        if crop_options is None:
            crop_options = setup["crop_options"] if calibrated or mode == current_mode else {}
        if not crop_options:
            st.info(ui["field_crops_unavailable"])
            return None
        crops = list(crop_options)
        valid_defaults = [crop_id for crop_id in crop_ids if crop_id in crop_options]
        irrigated = mode == "irrigated"
        with st.form(f"field-edit-{key}", border=False):
            soil_col, crop_col = st.columns(2)
            soil_type = soil_col.selectbox(
                ui["soil_type"], soils, index=soils.index(soil) if soil in soils else None, format_func=_soil_name,
            )
            if calibrated:
                chosen = crop_col.selectbox(
                    ui["crops"], crops, index=crops.index(valid_defaults[0]) if valid_defaults else None,
                    format_func=crop_options.__getitem__,
                )
                chosen_ids = (chosen,) if chosen else ()
            else:
                chosen_ids = tuple(crop_col.multiselect(
                    ui["crops"], crops, default=valid_defaults, format_func=crop_options.__getitem__, key=f"field-crops-{key}-{mode}",
                ))

            st.markdown(f'**{ui["my_limits"]}**')
            if irrigated:
                limit = st.number_input(
                    ui["irrigations_max"], min_value=0, step=1, value=setup.get("irrigations_per_year_max"),
                    help=ui["field_irrigation_unknown"], placeholder=ui["field_unknown"],
                )
            else:
                limit = None
            has_machinery = st.checkbox(ui["residue_machinery"], value=setup.get("has_residue_machinery", False))
            assured = calibrated and st.checkbox(ui["assured_market"], value=setup.get("prefer_assured_market", False))
            submitted = st.form_submit_button(ui["update_field"], type="primary")
        if submitted:
            if not soil_type:
                st.error(ui["field_soil_error"])
            elif not chosen_ids:
                st.error(ui["field_crop_error"])
            else:
                return soil_type, irrigated, chosen_ids, Constraints(limit, has_machinery, assured)
    return None


def _regional_water(story: dict, key: str) -> None:
    ui = labels()
    st.subheader(ui["storage"])
    place = story["site"]
    grace = story.get("grace") or {}
    slope = grace.get("trend_cm_per_yr")
    period = grace.get("period")
    if slope is None:
        st.caption(grace.get("note") or ui["storage_none"])
    else:
        if abs(slope) < .3:
            st.caption(ui["field_storage_weak"])
        else:
            tone = APP_COLOR["iron"] if slope < 0 else "#3D7FC4"
            direction = ui["storage_drier"] if slope < 0 else ui["storage_wetter"]
            magnitude = f"{abs(slope):.2f}"
            sentence = ui["field_storage_statement"].format(direction=direction.lower(), rate=magnitude)
            reading = escape(sentence).replace(magnitude, f"<strong>{magnitude}</strong>", 1)
            st.markdown(f'<p class="b-field-water-reading" style="color:{tone}">{reading}</p>', unsafe_allow_html=True)
        if period:
            st.caption(period)
    map_view(place["lat"], place["lon"], fixed=True, key=f"storage-{key}", trend=slope)
    if slope is not None:
        source = ". ".join(piece for piece in (grace.get("dataset"), grace.get("note")) if piece)
        st.caption(source or ui["storage_caption"])


def _cover_summary(bundle: dict) -> None:
    ui = labels()
    current = next(row for row in bundle["evidence"] if row["is_current"])
    bare = f'{current["metrics"]["bare_days"]["median"]:g}'
    st.markdown(
        f'<div class="b-field-reading"><h2>{escape(ui["field_cover_title"])}</h2>'
        f'<strong class="b-field-reading-value">{escape(bare)} <span>{escape(ui["field_cover_days"])}</span></strong>'
        f'<p>{escape(ui["field_cover_period"].format(seasons=current["n_seasons"]))}</p></div>',
        unsafe_allow_html=True,
    )


def _focus_chart(strata: dict, key: str) -> tuple[dict, tuple[str, ...]]:
    ui = labels()
    rows = sorted(strata["rows"], key=lambda row: row["season"])
    recent = 8
    years = {"all": ui["chart_years_all"]}
    if len(rows) > recent:
        years = {"recent": ui["chart_years_recent"].format(n=recent), **years}
    for row in reversed(rows):
        years[str(row["season"])] = farming_year_label(row["season"], strata["season_year_start"])
    markers = {"all": ui["chart_events_all"], "none": ui["chart_events_none"], **ui["events"]}
    periods_key, markers_key = f"chart-season-{key}", f"chart-events-{key}"
    default_period = next(iter(years))
    focused = (st.session_state.get(periods_key, default_period) != default_period
               or st.session_state.get(markers_key, "all") != "all")
    with st.expander(ui["chart_filter"], expanded=focused):
        seasons_col, markers_col = st.columns(2)
        period = seasons_col.selectbox(ui["chart_years_shown"], list(years), format_func=years.__getitem__,
                                       key=periods_key)
        selected = markers_col.selectbox(ui["chart_events_shown"], list(markers), format_func=markers.__getitem__,
                                          key=markers_key)
    if period == "recent":
        rows = rows[-recent:]
    elif period != "all":
        rows = [row for row in rows if row["season"] == int(period)]
    events = {"all": tuple(EVENTS), "none": ()}.get(selected, (selected,))
    return {**strata, "rows": rows}, events


def _pattern_sentence(pattern: dict, ui: dict) -> str:
    message = pattern["text"]
    if pattern["id"] == "bare" and message.startswith("Bare for "):
        return ui["field_bare_phrase"].format(period=message.removeprefix("Bare for "))
    return message


def field_view(
    bundle: dict, *, key: str, editor_open: bool = False,
) -> tuple[str, bool, tuple[str, ...], Constraints] | None:
    """Show the current rotation's patterns, field assumptions, and regional water."""
    ui = labels()
    story = bundle["field_story"]
    st.markdown(FIELD_STYLE, unsafe_allow_html=True)
    with st.container(key="field-summary"):
        reading, settings = st.columns([.57, .43], gap="large")
        with reading:
            _cover_summary(bundle)
        with settings:
            _field_facts(bundle["setup"])
            updated = field_inputs(bundle, key=key, editor_open=editor_open)
    history = bundle["strata"][story["current_rotation_id"]]
    with st.container(key="field-chart"):
        st.markdown(f'<div class="b-field-strata-title"><h2>{escape(ui["strata"])}</h2>'
                    f'<p>{escape(ui["chart_reading"])}</p></div>', unsafe_allow_html=True)
        graph = st.container()
        strata, events = _focus_chart(history, key)
        with graph:
            st.caption(ui["chart_visible_rows"].format(shown=len(strata["rows"]), total=len(history["rows"])))
            draw_strata(strata, key=f"current-strata-{key}", show_legend=False, events=events)
            draw_strata_legend([strata], events=events)
    with st.container(key="field-notes"):
        patterns = [pattern for pattern in story.get("patterns", ()) if pattern["id"] != "water_storage"]
        if patterns:
            st.subheader(ui["patterns"])
            points = "".join(f'<li>{escape(_pattern_sentence(pattern, ui))}</li>' for pattern in patterns)
            st.markdown(f'<ul class="b-field-pattern-list">{points}</ul>', unsafe_allow_html=True)
        with st.expander(ui["field_sources"]):
            notes, region = st.columns([.45, .55], gap="large")
            with notes:
                st.subheader(ui["calendar"])
                st.write(ui["calendar_source"][story["calendar_source"]])
                if story["ndvi_seasons_detected"]:
                    st.caption(ui["ndvi_detected"].format(n=story["ndvi_seasons_detected"]))
            with region:
                _regional_water(story, key)
    return updated
