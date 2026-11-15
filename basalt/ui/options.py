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
NUMBER = re.compile(r"\b\d+\b")
scenario_picker = components.declare_component(
    "basalt_climate_scenario", path=str(Path(__file__).with_name("scenario_component")),
)
OPTIONS_STYLE = """
<style>
.stApp .b-options-intro h2{font-size:clamp(25px,2.5vw,32px);line-height:1.16;margin:0 0 5px;padding:0}
.stApp .b-options-intro p{color:var(--ash);margin:0}
.stApp .b-rotation-reference{display:grid;grid-template-columns:minmax(165px,1fr) minmax(0,2.8fr);gap:20px;
 align-items:center;background:#ECEEEB;border:1px solid #D9DED8;border-radius:8px;padding:20px 22px}
.stApp .b-rotation-reference h3{padding:0;margin:3px 0 0;font-size:21px;line-height:1.2;overflow-wrap:anywhere}
.stApp .b-reference-kicker,.stApp .b-reference-period{display:block;color:var(--ash);font-size:13px}
.stApp .b-reference-kicker{font-weight:600}
.stApp .b-reference-period{margin-top:4px}
.stApp .b-reference-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin:0;gap:12px}
.stApp .b-reference-metrics div{border-inline-start:1px solid #CDD1CD;padding-inline-start:16px}
.stApp .b-reference-metrics dt{color:var(--ash);font-size:13px}
.stApp .b-reference-metrics dd{font-size:16px;font-weight:600;line-height:1.35;margin:3px 0 0}
.stApp .b-alternatives-title{font-size:20px;margin:10px 0 3px;padding:0}
.stApp .st-key-options-controls{margin-top:5px}
.stApp .b-scenario{margin:0;background:var(--plate);border-inline-start:2px solid var(--iron);font-size:14px}
.stApp :is(.st-key-options-grid,.st-key-options-charts) [data-testid="stHorizontalBlock"]{
 display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,245px),1fr));gap:16px;align-items:start}
.stApp :is(.st-key-options-grid,.st-key-options-charts) [data-testid="stHorizontalBlock"]>
 :is([data-testid="stColumn"],[data-testid="column"]){width:auto;min-width:0}
.stApp .st-key-options-grid [data-testid="stVerticalBlockBorderWrapper"]{background:var(--plate);border-radius:8px}
.stApp .st-key-options-grid [data-testid="stVerticalBlockBorderWrapper"]>.stVerticalBlock{row-gap:12px}
.stApp .st-key-options-single{max-width:650px}
.stApp .st-key-options-charts [data-testid="stPlotlyChart"]{max-width:100%;overflow-x:clip}
.stApp .b-replay-chart-name{font-size:15px;margin:0;padding:0;overflow-wrap:anywhere}
.stApp .b-option-title{min-block-size:4.45em}
.stApp .b-option-title h4{margin:4px 0 0;padding:0;font-size:20px;line-height:1.2;overflow-wrap:anywhere}
.stApp .b-option-lever{color:var(--ash);font-size:13px;font-weight:500}
.stApp .b-option-axes{margin:12px 0 0;padding:0}
.stApp .b-option-axis{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 8px;align-items:center;
 border-top:1px solid #EBECE9;padding:7px 0;font-size:14px;line-height:1.4}
.stApp .b-option-axis dt,.stApp .b-option-axis dd{margin:0}
.stApp .b-axis-direction{display:flex;gap:5px;align-items:center;border-radius:4px;font-size:13px;font-weight:600;
 line-height:1.3;padding:4px 7px;background:#F0F1EF;color:var(--ash)}
.stApp .b-axis-direction[data-tone="better"]{background:#EAF3ED;color:#295C3D}
.stApp .b-axis-direction[data-tone="worse"]{background:#F8EFEB;color:#882C2C}
.stApp .b-option-axis .b-count{white-space:nowrap}
.stApp .b-option-years{margin-bottom:4px}
.stApp .b-option-years .b-option-axis{display:block;padding:5px 0}
.stApp .b-option-years .b-option-axis dt{font-weight:600}
.stApp .b-option-years .b-axis-counts{color:var(--ash);white-space:normal}
.stApp .b-option-detail .b-verdict{min-height:0;font-weight:400;line-height:1.45;margin:0 0 6px}
.stApp .b-option-notices{display:grid;gap:5px;font-size:13px;line-height:1.4;color:var(--ash)}
.stApp .b-option-warning{padding-left:8px;border-inline-start:2px solid var(--iron);color:var(--basalt)}
.stApp .b-option-detail{border-top:1px solid var(--fracture);padding-top:8px}
.stApp .b-option-detail h4{font-size:14px;margin:0 0 4px;padding:0}
.stApp .b-option-detail p{font-size:14px;margin:0 0 6px}
.stApp :is(.st-key-options-grid,.st-key-options-secondary,.st-key-options-controls) summary{
 min-height:44px;padding-block:9px}
.stApp :is(.st-key-options-grid,.st-key-options-secondary,.st-key-options-controls) summary p{
 font-size:14px;font-weight:600;line-height:1.35}
.stApp :is(.st-key-options-grid,.st-key-options-secondary,.st-key-options-controls) summary:focus-visible{
 outline:2px solid var(--iron);outline-offset:-2px}
.stApp .st-key-options-grid summary p{color:var(--iron)}
@media(max-width:820px){
 .stApp .b-rotation-reference{grid-template-columns:1fr;gap:12px}
 .stApp .b-reference-metrics{border-top:1px solid #CDD1CD;padding-top:9px}
 .stApp .b-reference-metrics div:first-child{border-inline-start:0;padding-inline-start:0}
}
@media(max-width:600px){
 .stApp .b-rotation-reference{padding:13px 14px}
 .stApp .b-reference-metrics{gap:8px}
 .stApp .b-reference-metrics div{padding-inline-start:8px}
 .stApp .b-reference-metrics dd{font-size:14px}
 .stApp .b-option-title{min-block-size:0}
 .stApp .st-key-options-controls [data-testid="stHorizontalBlock"]{flex-wrap:wrap;gap:8px}
 .stApp .st-key-options-controls [data-testid="stHorizontalBlock"]>
 :is([data-testid="stColumn"],[data-testid="column"]){flex:1 1 calc(50% - 8px);min-width:0}
 .stApp .st-key-options-controls [data-testid="stHorizontalBlock"]:has(details[open])>
 :is([data-testid="stColumn"],[data-testid="column"]){flex-basis:100%}
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


def _reference(current: Evidence, irrigated: bool) -> None:
    ui = labels()
    metrics = current["metrics"]
    water_label = ui["option_water_irrigated"] if irrigated else ui["option_water_rainfed"]
    water = metrics["et_mm" if irrigated else "dry_stress_frac"]["median"]
    water_format = ui["option_reference_irr"] if irrigated else ui["option_reference_rf"]
    values = (
        (ui["soil"], ui["option_reference_soil"].format(score=metrics["soil_score"]["median"])),
        (water_label, water_format.format(water=water)),
        (ui["risk"], ui["option_reference_risk"].format(risk=metrics["risk_hits"]["median"])),
    )
    rows = "".join(f'<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>' for label, value in values)
    st.markdown(
        '<section class="b-rotation-reference"><div>'
        f'<span class="b-reference-kicker">{escape(ui["lever"]["current"])}</span>'
        f'<h3>{escape(current["name"])}</h3>'
        f'<span class="b-reference-period">{escape(ui["option_reference_period"])}</span></div>'
        f'<dl class="b-reference-metrics">{rows}</dl></section>',
        unsafe_allow_html=True,
    )


def _option_head(option: Evidence, irrigated: bool) -> None:
    ui = labels()
    water_ratings = ui["option_irrigated_ratings"] if irrigated else ui["option_rainfed_ratings"]
    specific_ratings = {"water": water_ratings, "risk": ui["option_risk_ratings"]}
    rows = []
    for axis in ("soil", "water", "risk"):
        tone = option["arrows"][axis]
        rating = specific_ratings.get(axis, {}).get(tone, ui["tone"][tone])
        rows.append(
            f'<div class="b-option-axis"><dt>{escape(ui[axis])}</dt>'
            f'<dd class="b-axis-direction" data-tone="{tone}">'
            f'<span aria-hidden="true">{ARROWS[tone]}</span>{escape(rating)}</dd></div>'
        )
    st.markdown(
        f'<div class="b-option-head" data-rotation="{escape(option["rotation_id"])}">'
        f'<div class="b-option-title"><span class="b-option-lever">{escape(ui["lever"][option["lever"]])}</span>'
        f'<h4>{escape(option["name"])}</h4></div><dl class="b-option-axes">{"".join(rows)}</dl></div>',
        unsafe_allow_html=True,
    )


def _option_notices(option: Evidence) -> None:
    notes = []
    if option["stability"]["badge"] == "depends" and not option["is_current"]:
        notes.append(f'<div>{escape(labels()["option_sensitive"])}</div>')
    notes.extend(f'<div class="b-option-warning">{escape(warning)}</div>' for warning in constraint_warnings(option))
    if notes:
        st.markdown(f'<div class="b-option-notices">{"".join(notes)}</div>', unsafe_allow_html=True)


def _year_results(option: Evidence) -> None:
    ui = labels()
    verdict = COUNT.sub(r'<span class="b-count">\g<0></span>', escape(option["verdict"]))
    rows = []
    if not option["is_current"]:
        for axis in ("soil", "water", "risk"):
            counts = ui["option_count_line"].format(**option["wins_vs_current"][axis])
            tally = NUMBER.sub(r'<span class="b-count">\g<0></span>', escape(counts))
            rows.append(f'<div class="b-option-axis"><dt>{escape(ui[axis])}</dt><dd class="b-axis-counts">{tally}</dd></div>')
    breakdown = f'<dl class="b-option-axes">{"".join(rows)}</dl>' if rows else ""
    heading = f'<h4>{escape(ui["option_years"])}</h4>' if rows else ""
    stability = f'<p>{escape(render_stability(option))}</p>' if rows else ""
    st.markdown(
        f'<section class="b-option-detail b-option-years" data-rotation="{escape(option["rotation_id"])}">'
        f'{heading}<p class="b-verdict">{verdict}</p>{breakdown}{stability}</section>',
        unsafe_allow_html=True,
    )


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


def _details(option: Evidence, current: Evidence, card: dict, *, title: str) -> None:
    ui = labels()
    with st.expander(title):
        _year_results(option)
        for section in ("why", "evidence", "benefits", "gaps", "risks"):
            lines = card.get(section, ())
            if isinstance(lines, str):
                lines = [lines]
            if not lines:
                continue
            heading = escape(ui[f"section_{section}"])
            items = "".join(f"<p>{escape(line)}</p>" for line in lines)
            st.markdown(f'<section class="b-option-detail"><h4>{heading}</h4>{items}</section>', unsafe_allow_html=True)
        _practices(option, current)


def _alternatives(options: list[Evidence], current: Evidence, bundle: dict) -> None:
    ui = labels()
    st.markdown(f'<h3 class="b-alternatives-title">{escape(ui["option_alternatives"])}</h3>', unsafe_allow_html=True)
    with st.container(key="options-grid"):
        with st.container(key="options-single" if len(options) == 1 else "options-columns"):
            for col, option in zip(st.columns(len(options)), options, strict=True):
                with col, st.container(border=True):
                    _option_head(option, bundle["setup"]["irrigated"])
                    _option_notices(option)
                    card = bundle.get("cards", {}).get(option["rotation_id"], {})
                    _details(option, current, card, title=ui["option_results"])
    st.caption(ui["option_count_guide"])


def _season_charts(options: list[Evidence], bundle: dict, *, key: str) -> None:
    ui = labels()
    views = [bundle["strata"][option["rotation_id"]] for option in options]
    alternate = {option["rotation_id"]: {**strata, "rows": strata["alternate_rows"]}
                 for option, strata in zip(options, views, strict=True) if strata.get("alternate_rows")}
    title = ui["option_charts"] if len(options) > 1 else ui["option_single_chart"]
    with st.expander(title):
        draw_strata_legend([*views, *alternate.values()])
        st.caption(ui["option_chart_guide"] if len(options) > 1 else ui["chart_reading"])
        with st.container(key="options-charts"):
            for col, option, strata in zip(st.columns(len(options)), options, views, strict=True):
                identity = option["rotation_id"]
                with col:
                    heading = option["name"]
                    if option["is_current"] and len(options) > 1:
                        heading += f' ({ui["lever"]["current"].lower()})'
                    st.markdown(f'<h3 class="b-replay-chart-name">{escape(heading)}</h3>', unsafe_allow_html=True)
                    draw_strata(strata, key=f"{key}-{identity}", thumbnail=True)
                    if identity in alternate:
                        st.caption(ui["phase_summary"])
                        st.markdown(
                            f'<h4 class="b-replay-chart-name">{escape(ui["phase_other"])}</h4>', unsafe_allow_html=True,
                        )
                        draw_strata(alternate[identity], key=f"{key}-{identity}-other", thumbnail=True)


def options_view(bundle: dict, *, key: str, on_scenario: Callable[[Scenario], None]) -> None:
    """Present the reference rotation, alternatives and archived replay evidence."""
    ui = labels()
    st.markdown(OPTIONS_STYLE, unsafe_allow_html=True)
    options = bundle["evidence"]
    current = next(option for option in options if option["is_current"])
    context = ui["options_context"].format(n=current["n_seasons"])
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
    _reference(current, bundle["setup"]["irrigated"])
    _option_notices(current)
    ordered = order_evidence(options, priorities)
    alternatives = [option for option in ordered if not option["is_current"]]
    if alternatives:
        _alternatives(alternatives, current, bundle)
    else:
        st.info(ui["no_options_available"])
    with st.container(key="options-secondary"):
        _season_charts(ordered, bundle, key=key)
        card = bundle.get("cards", {}).get(current["rotation_id"], {})
        _details(current, current, card, title=ui["option_reference_detail"])
        if current["tier"] == "global" and bundle.get("rejections"):
            with st.expander(ui["no_more"]):
                if len(alternatives) > 1 and len(alternatives) < 3:
                    st.write(ui["options_passed"].format(count=len(alternatives)))
                for entry in bundle["rejections"]:
                    lever = ui["lever"].get(entry["lever"], entry["lever"])
                    st.markdown(f'**{lever}**. {entry["reason"]}')
