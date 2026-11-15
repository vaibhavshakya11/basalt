from pathlib import Path

import streamlit.components.v1 as components

map_display = components.declare_component("basalt_field_map", path=str(Path(__file__).with_name("map_component")))


def map_view(lat: float, lon: float, *, key: str, fixed: bool = False, trend: float | None = None) -> dict | None:
    """Draw the field pin and optional regional trend without remote tiles."""
    return map_display(lat=lat, lon=lon, fixed=fixed, trend=trend, height=188 if fixed else 232,
                       key=key, default=None)
