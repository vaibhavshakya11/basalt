import re
from collections.abc import Callable
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from basalt.contracts import Evidence, Priorities, Scenario
from basalt.decision.priorities import order_evidence
from basalt.explain.cards import constraint_warnings, render_stability
from basalt.ui.components import APP_COLOR, ARROWS, copybook, labels
from basalt.ui.strata import draw_strata, draw_strata_legend

COUNT = re.compile(r"\b\d+ of \d+\b")
scenario_picker = components.declare_component(
    "basalt_climate_scenario", path=str(Path(__file__).with_name("scenario_component")),
)
OPTIONS_STYLE = """
<style>
.stApp .b-options-intro{margin-bottom:8px}
.stApp .b-options-intro h2{padding-top:0;margin:0}
.stApp .b-options-intro p{color:var(--ash);margin:0}
.stApp .b-scenario{margin:0;background:var(--plate);border-inline-start:2px solid var(--iron);font-size:14px}
.stApp .st-key-options-grid [data-testid="stVerticalBlockBorderWrapper"]{background:var(--plate)}
.stApp .st-key-options-grid :is([data-testid="stColumn"],[data-testid="column"]){min-width:0}
.stApp .st-key-options-grid [data-testid="stPlotlyChart"]{max-width:100%;overflow-x:clip}
.stApp .st-key-options-grid-single{max-width:620px}
.stApp .b-option-head{border-top:2px solid var(--fracture);padding-top:10px}
.stApp .b-option-head[data-current="true"]{border-color:var(--basalt)}
.stApp .b-option-head h3{margin:3px 0 8px;padding:0;font-size:18px;line-height:1.2;min-block-size:2.4em}
.stApp .b-option-lever{color:var(--ash);font-size:12px;font-weight:500}
.stApp .b-option-head .b-verdict{font-size:14px;line-height:1.4;min-block-size:5.6em;margin:0 0 10px;
 font-weight:400;overflow-wrap:anywhere}
.stApp .b-option-head .b-count{white-space:nowrap}
.stApp .b-option-axes{margin:0;padding:0}
.stApp .b-option-axis{display:flex;justify-content:space-between;align-items:center;gap:8px;
 border-top:1px solid var(--fracture);padding:5px 0;font-size:13px;line-height:1.4}
.stApp .b-option-axis dt,.stApp .b-option-axis dd{margin:0}
.stApp .b-option-axis dd{font-weight:600;white-space:nowrap}
.stApp .b-option-notes{display:grid;gap:4px;color:var(--ash);font-size:13px;line-height:1.4;min-block-size:2.8em}
.stApp .b-option-notes .b-tag{margin:0}
.stApp .b-option-warning{padding-left:8px;border-inline-start:2px solid var(--iron);color:var(--basalt)}
.stApp .b-option-detail{border-top:1px solid var(--fracture);padding-top:6px}
.stApp .b-option-detail h4{font-size:13px;margin:0 0 4px;padding:0}
.stApp .b-option-detail p{font-size:14px;margin:0 0 6px}
@media(max-width:980px){
 .stApp .st-key-options-grid [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
 .stApp .st-key-options-grid [data-testid="stHorizontalBlock"]>:is([data-testid="stColumn"],[data-testid="column"]){
   flex:1 1 calc(50% - 16px);min-width:0}
}
@media(max-width:600px){
 .stApp .st-key-options-controls [data-testid="stHorizontalBlock"]{flex-wrap:wrap;gap:8px}
 .stApp .st-key-options-controls [data-testid="stHorizontalBlock"]>:is([data-testid="stColumn"],[data-testid="column"]){
   flex:1 1 calc(50% - 8px);min-width:0}
 .stApp .st-key-options-controls [data-testid="stHorizontalBlock"]:has(details[open])>:is([data-testid="stColumn"],[data-testid="column"]){
   flex-basis:100%}
 .stApp .st-key-options-controls summary [data-testid="stMarkdownContainer"] p{font-size:14px;line-height:1.25}
 .stApp .st-key-options-grid [data-testid="stHorizontalBlock"]>:is([data-testid="stColumn"],[data-testid="column"]){
   flex:1 1 100%;min-width:0}
 .stApp .b-option-head h3,.stApp .b-option-head .b-verdict,.stApp .b-option-notes{min-block-size:0;min-height:0}
}
</style>
"""


def _scenario_from_event(event: object) -> Scenario | None:
    if not isinstance(event, dict):
        return None
    temperature, rainfall = event.get("temperature"), event.get("rainfall")
    if type(temperature) not in (int, float) or temperature not in (0, .5, 1, 1.5, 2, 2.5, 3):
        return None
    if type(rainfall) is not int or rainfall not in range(-30, 31, 5):
        return None
    return Scenario(float(temperature), round(1 + rainfall / 100, 2))


def _scenario_controls(current: Evidence, *, key: str, on_change: Callable[[Scenario], None]) -> None:
    ui = labels()
    applied = Scenario(**current["scenario"])
    with st.expander(ui["scenario"], expanded=applied != Scenario()):
        st.caption(ui["scenario_intro"])
        event = scenario_picker(
            temperature=applied.dT_c, rainfall=round((applied.rain_mult - 1) * 100),
            temperature_label=ui["warm"], rainfall_label=ui["rain"],
            apply_label=ui["scenario_apply"], reset_label=ui["scenario_reset"],
            key=f"scenario-controls-{key}", default=None,
        )
    scenario = _scenario_from_event(event)
    if scenario is None or not isinstance(event.get("receipt"), str):
        return
    receipts = st.session_state.setdefault("scenario_receipts", {})
    if receipts.get(key) == event["receipt"]:
        return
    receipts[key] = event["receipt"]
    if scenario != applied:
        on_change(scenario)
        st.rerun()


def _priorities(key: str) -> Priorities:
    ui = labels()
    with st.expander(ui["priorities"]):
        st.caption(ui["priorities_help"])
        weights = {
            axis: st.slider(ui[axis], 0.0, 1.0, 1.0, .05, key=f"priority-{key}-{axis}")
            for axis in ("soil", "water", "risk")
        }
    return Priorities(**weights)


def _render_scenario_status(current: Evidence) -> None:
    ui = labels()
    scenario = current["scenario"]
    if scenario["dT_c"] or scenario["rain_mult"] != 1:
        banner = ui["scenario_banner"].format(temperature=scenario["dT_c"], rain=round((scenario["rain_mult"] - 1) * 100))
        st.markdown(f'<div class="b-scenario" role="status">{escape(banner)}</div>', unsafe_allow_html=True)
        st.caption(ui["scenario_stability"])


def _option_head(option: Evidence) -> None:
    ui = labels()
    verdict = COUNT.sub(r'<span class="b-count">\g<0></span>', escape(option["verdict"]))
    rows = []
    for axis in ("soil", "water", "risk"):
        tone = option["arrows"][axis]
        rows.append(
            f'<div class="b-option-axis"><dt>{escape(ui[axis])}</dt>'
            f'<dd style="color:{APP_COLOR[tone]}"><span aria-hidden="true">{ARROWS[tone]}</span> '
            f'{escape(ui["tone"][tone])}</dd></div>'
        )
    st.markdown(
        f'<div class="b-option-head" data-current="{str(option["is_current"]).lower()}">'
        f'<div class="b-option-lever">{escape(ui["lever"][option["lever"]])}</div>'
        f'<h3>{escape(option["name"])}</h3>'
        f'<p class="b-verdict" data-rotation="{escape(option["rotation_id"])}">{verdict}</p>'
        f'<dl class="b-option-axes">{"".join(rows)}</dl></div>',
        unsafe_allow_html=True,
    )


def _option_notes(option: Evidence) -> None:
    tags = copybook()["tags"]
    notes = []
    tag_links = [
        f'<abbr title="{escape(tags[tag_id]["description"])}">{escape(tags[tag_id]["label"])}</abbr>'
        for tag_id in option["tags"] if tag_id in tags
    ]
    if tag_links:
        notes.append('<div class="b-tag">' + " · ".join(tag_links) + "</div>")
    if not option["is_current"]:
        notes.append(f'<div>{escape(render_stability(option))}</div>')
    notes.extend(f'<div class="b-option-warning">{escape(warning)}</div>' for warning in constraint_warnings(option))
    st.markdown(f'<div class="b-option-notes">{"".join(notes)}</div>', unsafe_allow_html=True)


def _practice_bar(metric: dict, color: str, label: str) -> str:
    central, low, high = (metric[key] for key in ("median", "p10", "p90"))
    extent = (high - low) * 100
    values = f"{label} {central:.2f}, {low:.2f} to {high:.2f}"
    return (
        f'<div class="b-practice-row"><span aria-label="{escape(values)}">{escape(label)} '
        f'<span class="b-count">{central:.2f}</span></span>'
        f'<div class="b-practice-track" title="{escape(values)}" style="background:#D5D8DB">'
        f'<span style="width:{central * 100}%;background:{color}"></span>'
        f'<i style="left:{low * 100}%;width:{extent}%"></i></div></div>'
    )


def _practices(option: Evidence, current: Evidence) -> None:
    ui = labels()
    fields = option["metrics"]["soil_factors"]
    current_fields = current["metrics"]["soil_factors"]
    titles = copybook()["soil_factors"]
    st.markdown(f'**{ui["soil_factors"]}**')
    st.caption(ui["soil_practices_caption"])
    for factor, comparison in fields.items():
        title = titles.get(factor, factor.replace("_", " ").capitalize())
        bars = _practice_bar(comparison, APP_COLOR["iron"], option["name"])
        if not option["is_current"]:
            bars += _practice_bar(current_fields[factor], APP_COLOR["ash"], current["name"])
        st.markdown(f'<div class="b-practice"><strong>{escape(title)}</strong>{bars}</div>', unsafe_allow_html=True)


def _details(option: Evidence, current: Evidence, card: dict) -> None:
    ui = labels()
    with st.expander(ui["details"]):
        for section in ("why", "evidence", "benefits", "gaps", "risks"):
            lines = card.get(section, ())
            if isinstance(lines, str):
                lines = [lines]
            heading = escape(ui[f"section_{section}"])
            items = "".join(f"<p>{escape(line)}</p>" for line in lines)
            st.markdown(f'<section class="b-option-detail"><h4>{heading}</h4>{items}</section>', unsafe_allow_html=True)
        _practices(option, current)


def _option_card(option: Evidence, current: Evidence, bundle: dict, *, key: str) -> None:
    ui = labels()
    identity = option["rotation_id"]
    card = bundle.get("cards", {}).get(identity, {})
    with st.container(border=True):
        _option_head(option)
        strata = bundle["strata"][identity]
        draw_strata(strata, key=f"{key}-{identity}", thumbnail=True)
        _option_notes(option)
        if strata.get("alternate_rows"):
            st.caption(ui["phase_summary"])
            with st.expander(ui["phase_other"]):
                other = dict(strata, rows=strata["alternate_rows"])
                draw_strata(other, key=f"{key}-{identity}-other", thumbnail=True)
        _details(option, current, card)


def options_view(bundle: dict, *, key: str, on_scenario: Callable[[Scenario], None]) -> None:
    """Present a comparable crop-rotation grid and controls for exploring the result."""
    ui = labels()
    st.markdown(OPTIONS_STYLE, unsafe_allow_html=True)
    options = bundle["evidence"]
    current = next(option for option in options if option["is_current"])
    context = ui["options_context"].format(current=current["name"], n=current["n_seasons"])
    st.markdown(
        f'<div class="b-options-intro"><h2>{escape(ui["options_title"])}</h2><p>{escape(context)}</p></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="options-controls"):
        priority_col, climate_col = st.columns(2)
        with priority_col:
            priorities = _priorities(key)
        with climate_col:
            _scenario_controls(current, key=key, on_change=on_scenario)
    _render_scenario_status(current)
    if len(options) == 1:
        st.info(ui["no_options_available"])
    ordered = order_evidence(options, priorities)
    with st.container(key="options-grid"):
        if len(ordered) == 1:
            with st.container(key="options-grid-single"):
                _option_card(current, current, bundle, key=key)
        else:
            for col, option in zip(st.columns(len(ordered)), ordered, strict=True):
                with col:
                    _option_card(option, current, bundle, key=key)
    draw_strata_legend([bundle["strata"][option["rotation_id"]] for option in ordered])
    if current["tier"] == "global" and bundle.get("rejections"):
        with st.expander(ui["no_more"], expanded=True):
            if len(options) > 1 and len(options) < 4:
                st.write(ui["options_passed"].format(count=len(options) - 1))
            for entry in bundle["rejections"]:
                lever = ui["lever"].get(entry["lever"], entry["lever"])
                st.markdown(f'**{lever}**. {entry["reason"]}')
