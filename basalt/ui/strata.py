from collections.abc import Sequence
from datetime import date, timedelta
from html import escape

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from basalt.calendar_utils import season_bounds
from basalt.ui.components import APP_COLOR, labels

COVER = {
    "bare": "#C8B79B", "Poaceae": "#7C9A5E", "Fabaceae": "#2F7F73",
    "Malvaceae": "#8E7FB5", "Brassicaceae": "#C9A73F",
}
EVENTS = {
    "heat": ("#C8423B", "triangle-up"),
    "frost": ("#3D7FC4", "diamond"),
    "rain": ("#7A4E2D", "circle"),
    "dry": ("#D9902F", "square"),
}


def _lighten(hex_color: str) -> str:
    rgb = bytes.fromhex(hex_color[1:])
    return "#" + bytes(round(channel * .73 + 255 * .27) for channel in rgb).hex()


COLORS = list(COVER.values()) + [_lighten(hex_color) for hex_color in list(COVER.values())[1:]]


def _color_scale() -> list:
    step = 1 / len(COLORS)
    return [[edge, color] for index, color in enumerate(COLORS) for edge in (index * step, (index + 1) * step)]


def _crop_palette(family: str, stage: str) -> int:
    family_index = tuple(COVER).index(family) if family in COVER else 0
    return family_index + (len(COVER) - 1 if family_index and stage in {"ini", "dev"} else 0)


def _strata_layers(
    strata: dict, width: int, thumbnail: bool, shown: Sequence[str],
) -> tuple[np.ndarray, list, dict]:
    ui = labels()
    rows = strata["rows"]
    start_month, start_day = map(int, strata["season_year_start"].split("-"))
    crop_color = np.full((len(rows), width), np.nan, dtype=np.float32)
    hover = []
    event_points = {event: ([], []) for event in EVENTS if event in shown}
    for line, row in enumerate(rows):
        start = date(row["season"], start_month, start_day)
        descriptions = [""] * width
        day_events = {}
        for event, days in row["events"].items():
            if event not in EVENTS:
                continue
            if event in event_points:
                xs, ys = event_points[event]
                xs.extend(days)
                ys.extend([row["season"]] * len(days))
            for day in days:
                day_events.setdefault(day, []).append(ui["events"][event])
        for first, last, crop, family, stage in row["segments"]:
            crop_color[line, first - 1:last] = _crop_palette(family, stage)
            if thumbnail:
                continue
            stage_label = ui["stages"].get(stage, stage).lower()
            cover = ui["chart_bare_hover"] if family == "bare" else ui["chart_crop_hover"].format(crop=crop, stage=stage_label)
            for day in range(first, last + 1):
                day_date = start + timedelta(days=day - 1)
                day_text = day_date.strftime("%d %b %Y")
                descriptions[day - 1] = f"<b>{day_text}</b><br>{escape(cover)}"
                weather = day_events.get(day)
                if weather:
                    event_labels = ", ".join(f"“{marker.lower()}”" for marker in weather)
                    annotation = ui["chart_event_hover"].format(events=event_labels)
                    descriptions[day - 1] += f"<br>{escape(annotation)}"
        if not thumbnail:
            hover.append(descriptions)
    return crop_color, hover, event_points


def _month_ticks(start: str, step: int) -> tuple[list[int], list[str]]:
    month, day = map(int, start.split("-"))
    season_start = date(2001, month, day)
    month_starts = [(1, season_start.strftime("%b"))]
    for offset in range(step, 12, step):
        next_month = (month - 1 + offset) % 12 + 1
        year = 2001 + int(next_month < month)
        first = date(year, next_month, 1)
        month_starts.append(((first - season_start).days + 1, first.strftime("%b")))
    positions, month_labels = zip(*month_starts, strict=True)
    return list(positions), list(month_labels)


def _base_layout(figure: go.Figure, *, height: int, thumbnail: bool) -> None:
    figure.update_layout(
        height=height, paper_bgcolor=APP_COLOR["paper"], plot_bgcolor=APP_COLOR["paper"],
        font={"family": "IBM Plex Sans, sans-serif", "color": APP_COLOR["ash"], "size": 12},
        margin={"l": 43 if thumbnail else 58, "r": 7, "t": 8, "b": 28},
        hoverlabel={"bgcolor": APP_COLOR["plate"], "font": {"color": APP_COLOR["basalt"]}},
        showlegend=False,
    )
    figure.update_xaxes(ticks="", showline=False, tickfont_size=10 if thumbnail else 11, fixedrange=True)
    figure.update_yaxes(ticks="", showline=False, tickfont_size=9 if thumbnail else 11, fixedrange=True)


def farming_year_label(year: int, start: str) -> str:
    """Name the actual calendar year or range covered by a farming year."""
    _, cutoff = season_bounds(year, start)
    last_year = (cutoff - timedelta(days=1)).year
    return str(year) if last_year == year else f"{year}/{last_year % 100:02d}"


def strata_figure(
    strata: dict, *, thumbnail: bool = False, include_legend: bool = False,
    events: Sequence[str] = tuple(EVENTS),
) -> go.Figure:
    """Build Season Strata from the archived daily crop and event segments."""
    rows = sorted(strata["rows"], key=lambda row: row["season"])
    strata = {**strata, "rows": rows}
    years = [row["season"] for row in rows]
    width = max(segment[1] for row in rows for segment in row["segments"])
    crop_color, hover, event_points = _strata_layers(strata, width, thumbnail, events)
    heatmap = go.Heatmap(
        x=list(range(1, width + 1)), y=years, z=crop_color, zmin=-.5, zmax=len(COLORS) - .5,
        colorscale=_color_scale(), showscale=False, ygap=2 if not thumbnail else 1,
        customdata=hover if not thumbnail else None, hoverongaps=False,
        hovertemplate="%{customdata}<extra></extra>" if not thumbnail else None,
        hoverinfo="skip" if thumbnail else None,
    )
    figure = go.Figure(heatmap)
    for name, (xs, ys) in event_points.items():
        if not xs:
            continue
        color, symbol = EVENTS[name]
        figure.add_scatter(
            x=xs, y=ys, mode="markers",
            marker={"color": color, "symbol": symbol, "size": 3 if thumbnail else 6,
                    "line": {"color": APP_COLOR["plate"], "width": 0 if thumbnail else .55}},
            hoverinfo="skip",
        )
    height = 140 if thumbnail else min(444, 160 + 13 * len(years))
    _base_layout(figure, height=height, thumbnail=thumbnail)
    month_ticks, month_labels = _month_ticks(strata["season_year_start"], 3 if thumbnail else 1)
    figure.update_xaxes(tickmode="array", tickvals=month_ticks, ticktext=month_labels, range=[.5, width + .5])
    year_ticks = list(dict.fromkeys((years[0], years[-1]))) if thumbnail else years
    figure.update_yaxes(tickmode="array", tickvals=year_ticks, range=[years[0] - .5, years[-1] + .5],
                        ticktext=[farming_year_label(year, strata["season_year_start"]) for year in year_ticks])
    if not thumbnail:
        ui = labels()
        figure.update_xaxes(title_text=ui["chart_month"], title_font_size=11, title_standoff=7, automargin=True)
        figure.update_yaxes(title_text=ui["chart_farming_year"], title_font_size=11, title_standoff=8, automargin=True)
        for month in month_ticks[1:]:
            figure.add_vline(x=month, line_color=APP_COLOR["plate"], line_width=.6, opacity=.44)
        for year in years[1:]:
            if year % 10 == 0:
                figure.add_hline(y=year - .5, line_color=APP_COLOR["plate"], line_width=2.2)
    if include_legend:
        _print_legend(figure, strata)
    return figure


def _marker(color: str, symbol: str) -> str:
    shapes = {
        "triangle-up": f'<path fill="{color}" d="M6 0 12 11H0Z"/>',
        "diamond": f'<path fill="{color}" d="M6 0 12 6 6 12 0 6Z"/>',
        "circle": f'<circle fill="{color}" cx="6" cy="6" r="5"/>',
        "square": f'<rect fill="{color}" x="1" y="1" width="10" height="10"/>',
    }
    return f'<svg viewBox="0 0 12 12" class="b-legend-mark" aria-hidden="true">{shapes[symbol]}</svg>'


def _legend_groups(views: Sequence[dict], events: Sequence[str]) -> dict[str, list[tuple[str, str, str]]]:
    ui = labels()
    families = {segment[3] for view in views for row in view["rows"] for segment in row["segments"]}
    crop_cover = [(ui["categories"][family], color, "square") for family, color in COVER.items() if family in families]
    weather = [(ui["events"][event], color, symbol) for event, (color, symbol) in EVENTS.items() if event in events]
    return {ui["chart_cover_legend"]: crop_cover, ui["chart_weather_legend"]: weather}


def _print_legend(figure: go.Figure, strata: dict) -> None:
    for group, items in _legend_groups([strata], tuple(EVENTS)).items():
        for index, (label, color, symbol) in enumerate(items):
            figure.add_scatter(
                x=[None], y=[None], mode="markers", showlegend=True, name=label, legendgroup=group,
                legendgrouptitle={"text": group, "font": {"size": 11}} if index == 0 else None,
                marker={"color": color, "symbol": symbol, "size": 9}, hoverinfo="skip",
            )
    figure.update_traces(showlegend=False, selector=lambda trace: not trace.name)
    figure.update_layout(showlegend=True, legend={"orientation": "h", "x": 0, "y": -.12, "yanchor": "top"},
                         margin={"l": 74, "r": 12, "t": 12, "b": 82}, height=492)


def draw_strata(
    strata: dict, *, key: str, thumbnail: bool = False, show_legend: bool = True,
    events: Sequence[str] = tuple(EVENTS),
) -> None:
    """Render a full or compact Season Strata chart."""
    st.plotly_chart(strata_figure(strata, thumbnail=thumbnail, events=events), use_container_width=True, key=key,
                    theme=None, config={"displayModeBar": False, "scrollZoom": False})
    if not thumbnail and show_legend:
        draw_strata_legend([strata], events=events)


LEGEND_STYLE = """
<style>
.stApp .b-chart-legend.b-strata-legend{display:flex;gap:10px 22px;align-items:flex-start;flex-wrap:wrap;margin:0}
.stApp .b-strata-legend section{border-top:1px solid var(--fracture);padding-top:5px;min-width:0}
.stApp .b-strata-legend h3{font-size:12px;line-height:1.3;padding:0;margin:0 0 4px;color:var(--basalt)}
.stApp .b-strata-legend-items{display:flex;gap:3px 12px;flex-wrap:wrap}
.stApp .b-strata-swatch{display:inline-block;width:18px;height:8px;margin-right:5px;vertical-align:0}
.stApp .b-strata-legend-key{white-space:nowrap}
.stApp .b-strata-legend .b-strata-legend-hint{font-size:12px;margin:0;color:var(--ash);flex-basis:100%}
@media(max-width:600px){
 .stApp .b-chart-legend.b-strata-legend{gap:8px}
 .stApp .b-strata-legend section{width:100%}
}
</style>
"""


def draw_strata_legend(views: Sequence[dict], *, events: Sequence[str] = tuple(EVENTS)) -> None:
    """Separate crop-cover swatches from the weather symbols that overlay them."""
    cover_group = labels()["chart_cover_legend"]
    groups = []
    for title, items in _legend_groups(views, events).items():
        if not items:
            continue
        entries = []
        for label, color, symbol in items:
            mark = (f'<span class="b-strata-swatch" style="background:{color}" aria-hidden="true"></span>'
                    if title == cover_group else _marker(color, symbol))
            entries.append(f'<span class="b-strata-legend-key">{mark}{escape(label)}</span>')
        groups.append(f'<section><h3>{escape(title)}</h3><div class="b-strata-legend-items">{"".join(entries)}</div></section>')
    hint = f'<p class="b-strata-legend-hint">{escape(labels()["chart_shading"])}</p>'
    st.markdown(
        LEGEND_STYLE + '<div class="b-chart-legend b-strata-legend">' + "".join(groups) + hint + "</div>",
        unsafe_allow_html=True,
    )
