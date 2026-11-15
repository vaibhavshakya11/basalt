import re
from html import escape

import streamlit as st

from basalt.contracts import Evidence, Priorities, Scenario
from basalt.decision.priorities import order_evidence
from basalt.explain.cards import constraint_warnings, render_stability
from basalt.ui.components import APP_COLOR, arrow_rows, copybook, labels
from basalt.ui.strata import draw_strata

COUNT = re.compile(r"\b\d+ of \d+\b")


def _scenario_controls(bundle: dict, *, key: str) -> Scenario | None:
    ui = labels()
    current = next(option for option in bundle["evidence"] if option["is_current"])
    scenario = current["scenario"]
    with st.expander(ui["scenario"], expanded=scenario != {"dT_c": 0, "rain_mult": 1}):
        with st.form(f"scenario-{key}", border=False):
            warm, rain = st.columns(2)
            temperature = warm.slider(ui["warm"], 0., 3., float(scenario["dT_c"]), step=.5, format="+%g °C")
            rainfall = rain.slider(ui["rain"], -30, 30, round((scenario["rain_mult"] - 1) * 100),
                                  step=5, format="%+d%%")
            if st.form_submit_button(ui["use_scenario"]):
                return Scenario(temperature, round(1 + rainfall / 100, 2))
    if scenario["dT_c"] or scenario["rain_mult"] != 1:
        st.info(ui["scenario_banner"].format(temperature=scenario["dT_c"],
                                            rain=round((scenario["rain_mult"] - 1) * 100)))
        st.caption(ui["scenario_stability"])
    return None


def _render_tags(option: Evidence) -> None:
    texts = copybook().get("tags", {})
    tags = []
    for tag_id in option["tags"]:
        entry = texts.get(tag_id, {})
        title = entry.get("label", tag_id.replace("_", " ").capitalize()) if isinstance(entry, dict) else tag_id.capitalize()
        definition = entry.get("description", title) if isinstance(entry, dict) else entry
        tags.append(f'<abbr title="{escape(definition)}">{escape(title)}</abbr>')
    if tags:
        st.markdown('<div class="b-tag">' + " · ".join(tags) + "</div>", unsafe_allow_html=True)


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
    titles = copybook().get("soil_factors", {})
    st.markdown(f'**{ui["soil_factors"]}**')
    for factor, comparison in fields.items():
        title = titles.get(factor, factor.replace("_", " ").capitalize())
        comparison_bars = _practice_bar(comparison, APP_COLOR["iron"], option["name"])
        if not option["is_current"]:
            comparison_bars += _practice_bar(current_fields[factor], APP_COLOR["ash"], current["name"])
        html = f'<div class="b-practice"><strong>{escape(title)}</strong>{comparison_bars}</div>'
        st.markdown(html, unsafe_allow_html=True)


def _option_card(option: Evidence, current: Evidence, bundle: dict, *, key: str) -> None:
    ui = labels()
    identity = option["rotation_id"]
    card = bundle.get("cards", {}).get(identity, {})
    with st.container(border=True):
        st.caption(ui["lever"][option["lever"]])
        st.markdown(f'### {option["name"]}')
        verdict = COUNT.sub(r'<span class="b-count">\g<0></span>', escape(option["verdict"]))
        st.markdown(f'<p class="b-verdict">{verdict}</p>', unsafe_allow_html=True)
        arrow_rows(option["arrows"])
        _render_tags(option)
        if not option["is_current"]:
            st.caption(render_stability(option))
        for warning in constraint_warnings(option):
            st.warning(warning)
        strata = bundle["strata"][identity]
        draw_strata(strata, key=f"{key}-{identity}", thumbnail=True)
        if strata.get("alternate_rows"):
            st.caption(ui["phase_summary"])
            with st.expander(ui["phase_other"]):
                other = dict(strata, rows=strata["alternate_rows"])
                draw_strata(other, key=f"{key}-{identity}-other", thumbnail=True)
        with st.expander(ui["details"]):
            for section in ("why", "evidence", "benefits", "gaps", "risks"):
                st.markdown(f'**{ui[f"section_{section}"]}**')
                lines = card.get(section, ())
                if isinstance(lines, str):
                    lines = [lines]
                for line in lines:
                    st.write(line)
            _practices(option, current)


def options_view(bundle: dict, *, key: str) -> Scenario | None:
    """Present scenario controls, comparisons and evidence."""
    ui = labels()
    st.subheader(ui["options_header"])
    with st.expander(ui["priorities"]):
        cols = st.columns(3)
        priorities = {axis: col.slider(ui[axis], 0., 1., 1., .05, key=f"priority-{key}-{axis}")
                      for axis, col in zip(("soil", "water", "risk"), cols, strict=True)}
    scenario = _scenario_controls(bundle, key=key)
    options = bundle["evidence"]
    current = next(option for option in options if option["is_current"])
    ordered = order_evidence(options, Priorities(**priorities))
    cols = st.columns([1] * len(ordered))
    for col, option in zip(cols, ordered, strict=True):
        with col:
            _option_card(option, current, bundle, key=key)
    if current["tier"] == "global" and bundle["rejections"]:
        with st.expander(ui["no_more"], expanded=True):
            if len(options) < 4:
                st.write(ui["options_passed"].format(count=len(options) - 1))
            for entry in bundle["rejections"]:
                lever = ui["lever"].get(entry["lever"], entry["lever"])
                st.markdown(f'**{lever}**. {entry["reason"]}')
    return scenario
