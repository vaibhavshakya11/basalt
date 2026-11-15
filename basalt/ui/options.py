import re
from collections.abc import Callable, Sequence
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

from basalt.contracts import Evidence, Priorities, Scenario
from basalt.decision.priorities import order_evidence
from basalt.explain.cards import constraint_warnings, render_stability
from basalt.ui.components import APP_COLOR, ARROWS, copybook, labels
from basalt.ui.strata import _month_ticks, draw_strata_legend, strata_figure

AXES = ("soil", "water", "risk")
NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
scenario_picker = components.declare_component(
    "basalt_climate_scenario", path=str(Path(__file__).with_name("scenario_component")),
)
OPTIONS_STYLE = Path(__file__).with_name("options_layout.css").read_text(encoding="utf-8")


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
    with st.popover(ui["scenario"]):
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
    with st.popover("What matters most"):
        st.caption(ui["priorities_help"])
        weights = {
            axis: st.slider(ui[axis], 0.0, 1.0, 1.0, .05, key=f"priority-{key}-{axis}")
            for axis in AXES
        }
    return Priorities(**weights)


def _numbers(text: str) -> str:
    return NUMBER.sub(r'<span class="b-count">\g<0></span>', escape(text))


def _render_scenario_status(current: Evidence) -> None:
    ui = labels()
    scenario = current["scenario"]
    temperature, rain = scenario["dT_c"], round((scenario["rain_mult"] - 1) * 100)
    if temperature or rain:
        label = ui["scenario_banner"].format(temperature=temperature, rain=rain)
        rainfall = f"{abs(rain)}% {'less' if rain < 0 else 'more'} rain" if rain else "unchanged rainfall"
        message = f"Showing {temperature:+g} °C, {rainfall}. {ui['scenario_stability']}"
        st.markdown(f'<p class="b-scenario" role="status" aria-label="{escape(label)}">{_numbers(message)}</p>',
                    unsafe_allow_html=True)


def _answer(options: Sequence[Evidence], irrigated: bool) -> str:
    alternatives = [option for option in options if not option["is_current"]]
    if not alternatives:
        return labels()["no_options_available"]
    eligible = [option for option in alternatives if "better" in option["arrows"].values()
                and "worse" not in option["arrows"].values()]
    if not eligible:
        if all("better" in option["arrows"].values() for option in alternatives):
            return "Every option trades one benefit against another. Compare them below."
        if any("better" in option["arrows"].values() for option in alternatives):
            return "The improvements come with trade-offs. Compare them below."
        return "No alternative showed a clear improvement on these measures."
    best = max(eligible, key=lambda option: tuple(option["arrows"].values()).count("better"))
    readings = {"soil": "had a better soil score", "water": "used less water" if irrigated else "had less water stress",
                "risk": "had lower weather risk"}
    better = [f"{readings[axis]} in {best['wins_vs_current'][axis]['better']:g} of {best['n_seasons']} seasons"
              for axis in AXES if best["arrows"][axis] == "better"]
    similar = [labels()[axis].lower() for axis in AXES if best["arrows"][axis] == "similar"]
    benefit = ", ".join(better[:-1]) + " and " + better[-1] if len(better) > 1 else better[0]
    context = f", with similar {' and '.join(similar)}" if similar else ""
    return f"{best['name']} {benefit}{context}."


def _target(option: Evidence) -> str:
    return escape(f"rotation-evidence-{option['rotation_id']}")


def _metric(option: Evidence, axis: str, irrigated: bool) -> tuple[str, str]:
    metrics = option["metrics"]
    if axis == "soil":
        return f"{metrics['soil_score']['median']:.0f}", "/ 100"
    if axis == "risk":
        return f"{metrics['risk_hits']['median']:.1f}", "hits/yr"
    if irrigated:
        return f"{metrics['et_mm']['median']:,.0f}", "mm/yr"
    return f"{metrics['dry_stress_frac']['median']:.0%}", "of sensitive days stressed"


def _measure_cell(option: Evidence, axis: str, irrigated: bool) -> str:
    ui = labels()
    tone = option["arrows"][axis]
    value, unit = _metric(option, axis, irrigated)
    rating = ""
    if not option["is_current"]:
        count_key = "tie" if tone == "similar" else tone
        count = option["wins_vs_current"][axis][count_key]
        tied = " tied" if tone == "similar" else ""
        word = ui["tone"][tone]
        if axis == "water" and tone != "similar":
            word = "Less" if tone == "better" else "More"
        rating = (f'<span class="b-option-status" data-tone="{tone}"><span aria-hidden="true">{ARROWS[tone]}</span> {word}</span>'
                  f'<span class="b-option-tally"><span class="b-count">{count:g} of {option["n_seasons"]}</span>{tied}</span>')
    pumping = (f'<span class="b-option-pumping">pumped <span class="b-count">{option["metrics"]["irr_gross_mm"]["median"]:,.0f}</span> mm</span>'
               if axis == "water" and irrigated else "")
    return (f'<td role="cell"><span class="b-option-mobile-label" aria-hidden="true">{escape(ui[axis])}</span>'
            f'{rating}<span class="b-option-value"><span class="b-count">{value}</span> {_numbers(unit)}</span>{pumping}</td>')


def _comparison_row(option: Evidence, irrigated: bool) -> str:
    ui = labels()
    current = option["is_current"]
    subtitle = "Your current rotation" if current else ui["lever"][option["lever"]]
    warnings = "".join(f'<span class="b-option-warning">{_numbers(warning)}</span>' for warning in constraint_warnings(option))
    verdict = "" if current else f'<span class="b-verdict">{_numbers(option["verdict"])}</span>'
    stability = render_stability(option)
    if option["stability"]["badge"] == "robust":
        stability = "Holds under tested assumptions"
    if current:
        stability = ""
    identity = escape(option["rotation_id"])
    name = escape(option["name"])
    detail = f'<a href="#{_target(option)}" class="b-text-link b-option-details" aria-label="Details for {name}">Details</a>'
    cells = "".join(_measure_cell(option, axis, irrigated) for axis in AXES)
    return (f'<tr role="row" data-current="{str(current).lower()}" data-rotation="{identity}">'
            f'<th role="rowheader" scope="row"><span class="b-option-lever">{escape(subtitle)}</span>'
            f'<strong class="b-option-name">{name}</strong>{verdict}{warnings}</th>{cells}'
            f'<td class="b-option-stability" role="cell"><span class="b-option-mobile-label" aria-hidden="true">Stability</span>'
            f'<span>{escape(stability)}</span>{detail}</td></tr>')


def _option_head(option: Evidence, irrigated: bool, *, alternatives: Sequence[Evidence] = ()) -> None:
    ui = labels()
    headings = ("Option", ui["soil"], ui["water"], ui["risk"], "Stability")
    header = "".join(f'<th role="columnheader" scope="col">{escape(heading)}</th>' for heading in headings)
    rows = "".join(_comparison_row(row, irrigated) for row in (option, *alternatives))
    st.markdown(
        '<div id="rotation-comparison" class="b-option-table-wrap" tabindex="-1"><table class="b-v2-table b-option-table" '
        'aria-label="Crop rotation comparison" role="table">'
        f'<thead role="rowgroup"><tr role="row">{header}</tr></thead><tbody role="rowgroup">{rows}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def _detail_copy(option: Evidence, card: dict) -> str:
    ui = labels()
    breakdown = ""
    if not option["is_current"]:
        counts = "".join(f'<div><dt>{escape(ui[axis])}</dt><dd class="b-axis-counts">'
                         f'{_numbers(ui["option_count_line"].format(**option["wins_vs_current"][axis]))}</dd></div>'
                         for axis in AXES)
        breakdown = f'<dl aria-label="{escape(ui["option_years"])}">{counts}</dl>'
    sections = []
    for section in ("why", "evidence", "benefits", "gaps", "risks"):
        lines = card.get(section, ())
        if isinstance(lines, str):
            lines = [lines]
        extra = breakdown if section == "evidence" else ""
        if lines or extra:
            title = escape(ui[f"section_{section}"])
            paragraphs = "".join(f"<p>{_numbers(line)}</p>" for line in lines)
            sections.append(f"<section><h4>{title}</h4>{paragraphs}{extra}</section>")
    return "".join(sections)


def _plot_mark(metric: dict, kind: str, name: str) -> str:
    midpoint, low, high = (metric[key] for key in ("median", "p10", "p90"))
    values = f"{name}. Median {midpoint:.2f}, 10th to 90th percentile {low:.2f} to {high:.2f}"
    return (f'<div class="b-factor-mark" data-kind="{kind}" role="img" aria-label="{escape(values)}" title="{escape(values)}">'
            f'<span class="b-factor-interval" style="left:{low * 100:g}%;width:{(high - low) * 100:g}%"></span>'
            f'<span class="b-factor-dot" style="left:{midpoint * 100:g}%"></span></div>')


def _factor_plot(option: Evidence, current: Evidence) -> str:
    ui, copy = labels(), copybook()
    fields = option["metrics"]["soil_factors"]
    reference = current["metrics"]["soil_factors"]
    base = escape(current["name"])
    tags = " · ".join(f'<abbr title="{escape(copy["tags"][tag]["description"])}">{escape(copy["tags"][tag]["label"])}</abbr>'
                      for tag in option["tags"] if tag in copy["tags"])
    legend = f'<span class="b-factor-label" data-kind="current">{base}</span>'
    if not option["is_current"]:
        legend += f'<span class="b-factor-label" data-kind="alternative">{escape(option["name"])}</span>'
    rows = []
    for factor, metric in fields.items():
        name = copy["soil_factors"].get(factor, factor.replace("_", " ").capitalize())
        marks = _plot_mark(reference[factor], "current", current["name"])
        if not option["is_current"]:
            marks += _plot_mark(metric, "alternative", option["name"])
        rows.append(f'<div class="b-factor-row"><span>{escape(name)}</span><div>{marks}</div></div>')
    tags_line = f'<p class="b-option-tags">{tags}</p>' if tags else ""
    scale = '<div class="b-factor-scale"><span class="b-count">0</span><span class="b-count">0.5</span><span class="b-count">1</span></div>'
    return (f'<section><h4>{escape(ui["soil_factors"])}</h4><p>Dots show medians. Lines span the tenth to ninetieth '
            f'percentiles.</p><div class="b-factor-legend">{legend}</div>{"".join(rows)}'
            f'<div class="b-factor-row b-factor-axis"><span></span>{scale}</div>{tags_line}</section>')


def _year_results(option: Evidence, current: Evidence | None = None, card: dict | None = None) -> None:
    title = escape(option["name"])
    copy = _detail_copy(option, card or {})
    chart = _factor_plot(option, current) if current is not None else ""
    st.markdown(f'<section class="b-option-evidence b-surface" id="{_target(option)}" tabindex="-1" aria-label="Evidence for {title}">'
                f'<header><h3>{title}</h3><a class="b-text-link" href="#rotation-comparison">Close details</a></header>'
                f'<div class="b-option-evidence-layout"><div>{copy}</div>{chart}</div></section>', unsafe_allow_html=True)


def _season_charts(options: Sequence[Evidence], bundle: dict, *, key: str) -> None:
    ui = labels()
    panels = []
    for option in options:
        strata = bundle["strata"][option["rotation_id"]]
        name = option["name"]
        if option["is_current"]:
            name += " · current rotation"
        panels.append((name, strata))
        if strata.get("alternate_rows"):
            panels.append((f"{option['name']} · other starting crop", {**strata, "rows": strata["alternate_rows"]}))
    count = len(panels)
    figure = make_subplots(rows=count, cols=1, shared_xaxes=True, vertical_spacing=.25 / count)
    width = 0
    for row, (name, strata) in enumerate(panels, 1):
        chart = strata_figure(strata, thumbnail=True)
        figure.add_traces(chart.data, rows=[row] * len(chart.data), cols=[1] * len(chart.data))
        axis = chart.layout.yaxis
        figure.update_yaxes(tickmode="array", tickvals=axis.tickvals, ticktext=axis.ticktext, range=axis.range,
                            tickfont_size=9, fixedrange=True, row=row, col=1)
        width = max(width, len(chart.data[0].x))
        yref = "y domain" if row == 1 else f"y{row} domain"
        figure.add_annotation(xref="paper", yref=yref, x=0, y=1, xanchor="left", yanchor="bottom", yshift=3,
                              text=escape(name), align="left", showarrow=False, font={"size": 12, "color": APP_COLOR["basalt"]})
    ticks, months = _month_ticks(panels[0][1]["season_year_start"], 1)
    figure.update_xaxes(range=[.5, width + .5], fixedrange=True, tickmode="array", tickvals=ticks, ticktext=months,
                        tickfont_size=10, ticks="", showgrid=False)
    figure.update_layout(height=130 * count + 55, paper_bgcolor=APP_COLOR["paper"], plot_bgcolor=APP_COLOR["paper"],
                         showlegend=False, margin={"l": 48, "r": 14, "t": 27, "b": 32},
                         font={"family": "IBM Plex Sans, sans-serif", "color": APP_COLOR["ash"]})
    st.subheader(ui["strata"])
    st.plotly_chart(figure, use_container_width=True, theme=None, key=f"options-strata-{key}",
                    config={"displayModeBar": False, "scrollZoom": False})
    draw_strata_legend([strata for _, strata in panels])
    if count > len(options):
        st.caption("Two-year rotations show both starting crops. The comparison averages their results.")


def options_view(bundle: dict, *, key: str, on_scenario: Callable[[Scenario], None]) -> None:
    """Compare archived rotation results and inspect the evidence for one rotation."""
    ui = labels()
    st.markdown(f"<style>{OPTIONS_STYLE}</style>", unsafe_allow_html=True)
    options = bundle["evidence"]
    current = next(option for option in options if option["is_current"])
    irrigated = bundle["setup"]["irrigated"]
    st.markdown(f'<h2 id="your-options">{escape(ui["options_title"])}</h2>'
                f'<p class="b-v2-answer">{_numbers(_answer(options, irrigated))}</p>', unsafe_allow_html=True)
    with st.container(key="options-controls"):
        _, priority_col, climate_col = st.columns([2.7, 1, 1], gap="small")
        with priority_col:
            priorities = _priorities(key)
        with climate_col:
            _scenario_controls(current, key=key, on_change=on_scenario)
    _render_scenario_status(current)
    ordered = order_evidence(options, priorities)
    _option_head(current, irrigated, alternatives=ordered[1:])
    with st.container(key="options-details"):
        for option in ordered:
            card = bundle.get("cards", {}).get(option["rotation_id"], {})
            _year_results(option, current, card)
    if current["tier"] == "global" and bundle.get("rejections"):
        st.markdown(f'**{ui["no_more"]}**\n\n' + "\n".join(
            f'- **{ui["lever"].get(entry["lever"], entry["lever"])}.** {entry["reason"]}' for entry in bundle["rejections"]
        ))
    with st.container(key="options-strata"):
        _season_charts(ordered, bundle, key=key)
