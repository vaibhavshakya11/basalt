from html import escape

import streamlit as st

from basalt.contracts import Constraints
from basalt.ui.components import APP_COLOR, labels, text_with_numbers
from basalt.ui.map import map_view
from basalt.ui.strata import EVENTS, draw_strata, draw_strata_legend, farming_year_label

FIELD_STYLE = """
<style>
.stApp .st-key-field-chart{margin-top:16px}
.stApp .st-key-field-chart .b-strata-legend section{border:0;display:flex;align-items:baseline;gap:8px}
.stApp .st-key-field-chart .b-strata-legend h3{margin:0;white-space:nowrap}
.stApp .st-key-field-chart [data-testid="stPlotlyChart"]{max-width:100%;overflow-x:clip}
.stApp .st-key-field-patterns,.stApp .st-key-field-assumptions{margin-top:40px}
.stApp .b-field-pattern-list{margin:0;padding-inline-start:28px;max-width:70ch}
.stApp .b-field-pattern-list li{margin:0 0 8px;padding-inline-start:6px}
.stApp .b-field-pattern-list li::marker{font-family:'IBM Plex Mono',monospace;color:var(--ash)}
.stApp .b-field-facts{display:grid;grid-template-columns:minmax(104px,1fr) minmax(0,1.55fr);gap:0 16px;margin:0 0 16px}
.stApp .b-field-fact{display:contents}
.stApp .b-field-fact dt{color:var(--ash);margin:0;align-self:center}
.stApp .b-field-fact dd{display:flex;align-items:center;gap:12px;margin:0;overflow-wrap:anywhere}
.stApp .b-field-fact a{display:inline-flex;align-items:center;min-height:40px;font-size:var(--type-xs)}
.stApp .b-field-calendar h3{font-size:var(--type-sm)}
.stApp .b-field-calendar p{margin:0;max-width:58ch}
.stApp .st-key-field-editor details{border:0;background:transparent}
.stApp .st-key-field-editor details summary{padding-inline:0;min-height:40px;color:var(--iron);font-weight:600}
.stApp .st-key-field-editor details summary p{color:inherit}
.stApp .b-field-water-reading{margin:0 0 4px;font-weight:600}
.stApp .st-key-field-cta{margin-top:24px}
@media(max-width:767px){
 .stApp .st-key-field-patterns,.stApp .st-key-field-assumptions{margin-top:24px}
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
        f'<div class="b-field-fact"><dt>{escape(label)}</dt><dd><span>{escape(value)}</span>'
        f'<a href="#edit-field-settings" class="b-text-link" aria-label="Edit {escape(label.lower())}" data-field-edit>Edit</a>'
        '</dd></div>'
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
            tone = APP_COLOR["iron"] if slope < 0 else APP_COLOR["basalt"]
            direction = ui["storage_drier"] if slope < 0 else ui["storage_wetter"]
            magnitude = f"{abs(slope):.2f}"
            sentence = ui["field_storage_statement"].format(direction=direction.lower(), rate=magnitude)
            reading = text_with_numbers(sentence)
            st.markdown(f'<p class="b-field-water-reading" style="color:{tone}">{reading}</p>', unsafe_allow_html=True)
        if period:
            st.markdown(f'<p class="b-field-context">{text_with_numbers(period)}</p>', unsafe_allow_html=True)
    map_view(place["lat"], place["lon"], fixed=True, key=f"storage-{key}", trend=slope)
    if slope is not None:
        source = ". ".join(piece for piece in (grace.get("dataset"), grace.get("note")) if piece)
        st.caption(source or ui["storage_caption"])


def _field_answer(bundle: dict) -> None:
    ui = labels()
    current = next(row for row in bundle["evidence"] if row["is_current"])
    story = bundle["field_story"]
    soil_class = bundle["setup"]["soil_class"]
    soil = _soil_name(soil_class).lower() if soil_class else "unspecified"
    description = f'This replay follows {current["name"].lower()} on {soil} soil.'
    patterns = [_pattern_sentence(pattern, ui) for pattern in story.get("patterns", ())
                if pattern["id"] in {"bare", "vulnerable"}]
    st.markdown(f'<p class="b-v2-answer">{text_with_numbers(" ".join([description, *patterns]))}</p>',
                unsafe_allow_html=True)


def _focus_chart(strata: dict, key: str) -> tuple[dict, tuple[str, ...]]:
    ui = labels()
    rows = sorted(strata["rows"], key=lambda row: row["season"])
    recent = 8
    years = {"all": ui["chart_years_all"]}
    if len(rows) > recent:
        years["recent"] = ui["chart_years_recent"].format(n=recent)
    for row in reversed(rows):
        years[str(row["season"])] = farming_year_label(row["season"], strata["season_year_start"])
    markers = {"all": ui["chart_events_all"], "none": ui["chart_events_none"], **ui["events"]}
    periods_key, markers_key = f"chart-season-{key}", f"chart-events-{key}"
    focused = (st.session_state.get(periods_key, "all") != "all"
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
    if pattern["id"] == "water_storage":
        return message.replace("Water stored on land in this region (~300 km)", "Regional water storage (about 300 km)")
    return message


def field_view(
    bundle: dict, *, key: str, editor_open: bool = False,
) -> tuple[str, bool, tuple[str, ...], Constraints] | None:
    """Show the current rotation's patterns, field assumptions, and regional water."""
    ui = labels()
    story = bundle["field_story"]
    st.markdown(FIELD_STYLE, unsafe_allow_html=True)
    _field_answer(bundle)
    history = bundle["strata"][story["current_rotation_id"]]
    with st.container(key="field-chart"):
        st.markdown(f'## {ui["strata"]}')
        st.caption(ui["chart_reading"])
        graph = st.container()
        strata, events = _focus_chart(history, key)
        with graph:
            if len(strata["rows"]) != len(history["rows"]):
                count = ui["chart_visible_rows"].format(shown=len(strata["rows"]), total=len(history["rows"]))
                st.markdown(f'<p class="b-field-context">{text_with_numbers(count)}</p>', unsafe_allow_html=True)
            draw_strata(strata, key=f"current-strata-{key}", show_legend=False, events=events)
            draw_strata_legend([strata], events=events)
    patterns = sorted(story.get("patterns", ()), key=lambda pattern: pattern["id"] == "water_storage")
    if patterns:
        with st.container(key="field-patterns"):
            st.subheader(ui["patterns"])
            points = "".join(f'<li>{text_with_numbers(_pattern_sentence(pattern, ui))}</li>' for pattern in patterns)
            st.markdown(f'<ol class="b-field-pattern-list">{points}</ol>', unsafe_allow_html=True)
    with st.container(key="field-assumptions"):
        notes, region = st.columns([.5, .5], gap="large")
        with notes:
            st.subheader("What we assumed about your field")
            _field_facts(bundle["setup"])
            source = ui["calendar_source"][story["calendar_source"]]
            st.markdown(f'<div class="b-field-calendar"><h3>{escape(ui["calendar"])}</h3>'
                        f'<p>{escape(source)}</p></div>', unsafe_allow_html=True)
            if story["ndvi_seasons_detected"]:
                detection = ui["ndvi_detected"].format(n=story["ndvi_seasons_detected"])
                st.markdown(f'<p class="b-field-context">{text_with_numbers(detection)}</p>', unsafe_allow_html=True)
            with st.container(key="field-editor"):
                st.markdown('<span id="edit-field-settings"></span>', unsafe_allow_html=True)
                updated = field_inputs(bundle, key=key, editor_open=editor_open)
        with region:
            _regional_water(story, key)
    with st.container(key="field-cta"):
        st.markdown('<a class="b-primary-link" href="#your-options" data-options-step>See your options &rarr;</a>',
                    unsafe_allow_html=True)
    return updated
