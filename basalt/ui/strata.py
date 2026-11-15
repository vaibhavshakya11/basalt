from datetime import date, timedelta
from html import escape

import numpy as np
import plotly.graph_objects as go
import streamlit as st

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


def _strata_layers(strata: dict, width: int, thumbnail: bool) -> tuple[np.ndarray, list, dict]:
    ui = labels()
    rows = strata["rows"]
    start_month, start_day = map(int, strata["season_year_start"].split("-"))
    crop_color = np.full((len(rows), width), np.nan, dtype=np.float32)
    hover = []
    event_points = {event: ([], []) for event in EVENTS}
    for line, row in enumerate(rows):
        start = date(row["season"], start_month, start_day)
        descriptions = [""] * width
        day_events = {}
        for event, days in row["events"].items():
            if event not in EVENTS:
                continue
            xs, ys = event_points[event]
            xs.extend(days)
            ys.extend([row["season"]] * len(days))
            for day in days:
                day_events.setdefault(day, []).append(ui["events"][event])
        for first, last, crop, family, stage in row["segments"]:
            crop_color[line, first - 1:last] = _crop_palette(family, stage)
            if thumbnail:
                continue
            stage_label = ui["stages"].get(stage, stage)
            for day in range(first, last + 1):
                day_date = start + timedelta(days=day - 1)
                day_text = day_date.strftime("%d %b %Y")
                weather = "".join(f"<br>{escape(mark)}" for mark in day_events.get(day, ()))
                descriptions[day - 1] = f"{day_text}<br>{escape(crop)}<br>{escape(stage_label)}{weather}"
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


def strata_figure(strata: dict, *, thumbnail: bool = False, include_legend: bool = False) -> go.Figure:
    """Build Season Strata from the archived daily crop and event segments."""
    rows = strata["rows"]
    years = [row["season"] for row in rows]
    width = max(segment[1] for row in rows for segment in row["segments"])
    crop_color, hover, event_points = _strata_layers(strata, width, thumbnail)
    heatmap = go.Heatmap(
        x=list(range(1, width + 1)), y=years, z=crop_color, zmin=-.5, zmax=len(COLORS) - .5,
        colorscale=_color_scale(), showscale=False, ygap=2 if not thumbnail else 1,
        customdata=hover if not thumbnail else None, hoverongaps=False,
        hovertemplate="%{customdata}<extra></extra>" if not thumbnail else None,
        hoverinfo="skip" if thumbnail else None,
    )
    figure = go.Figure(heatmap)
    for name, (color, symbol) in EVENTS.items():
        xs, ys = event_points[name]
        if xs:
            figure.add_scatter(
                x=xs, y=ys, mode="markers", marker={"color": color, "symbol": symbol, "size": 3 if thumbnail else 6},
                hoverinfo="skip",
            )
    _base_layout(figure, height=140 if thumbnail else 420, thumbnail=thumbnail)
    month_ticks, month_labels = _month_ticks(strata["season_year_start"], 3 if thumbnail else 1)
    figure.update_xaxes(tickmode="array", tickvals=month_ticks, ticktext=month_labels, range=[.5, width + .5])
    year_ticks = [years[0], years[-1]] if thumbnail else years
    figure.update_yaxes(tickmode="array", tickvals=year_ticks, range=[min(years) - .5, max(years) + .5],
                        ticktext=[f"{year}/{(year + 1) % 100:02d}" for year in year_ticks])
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


def _visible_legend(strata: dict) -> list[tuple[str, str, str]]:
    ui = labels()
    families = {segment[3] for row in strata["rows"] for segment in row["segments"]}
    categories = [(ui["categories"][family], color, "square") for family, color in COVER.items() if family in families]
    events = [(ui["events"][event], color, symbol) for event, (color, symbol) in EVENTS.items()]
    return categories + events


def _print_legend(figure: go.Figure, strata: dict) -> None:
    for label, color, symbol in _visible_legend(strata):
        figure.add_scatter(x=[None], y=[None], mode="markers", showlegend=True, name=label,
                           marker={"color": color, "symbol": symbol, "size": 9}, hoverinfo="skip")
    figure.update_traces(showlegend=False, selector=lambda trace: not trace.name)
    figure.update_layout(showlegend=True, legend={"orientation": "h", "x": 0, "y": -.06, "yanchor": "top"},
                         margin={"l": 66, "r": 12, "t": 12, "b": 68}, height=480)


def draw_strata(strata: dict, *, key: str, thumbnail: bool = False) -> None:
    """Render a full or compact Season Strata chart."""
    st.plotly_chart(strata_figure(strata, thumbnail=thumbnail), use_container_width=True, key=key,
                    theme=None, config={"displayModeBar": False, "scrollZoom": False})
    if thumbnail:
        return
    legend = [
        f'<span>{_marker(color, symbol)}{escape(label)}</span>'
        for label, color, symbol in _visible_legend(strata)
    ]
    st.markdown('<div class="b-chart-legend">' + "".join(legend) + "</div>", unsafe_allow_html=True)
    st.caption(labels()["chart_shading"])
