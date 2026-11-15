import re
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

from basalt.config import SCOPE
from basalt.knowledge.loader import read_yaml

APP_COLOR = {
    "basalt": "#24272B", "ash": "#5F656C", "fracture": "#D5D8DB", "paper": "#F7F7F6",
    "plate": "#FFFFFF", "iron": "#A4472A", "better": "#2E6A47", "similar": "#5F656C",
    "worse": "#9B2D2D",
}
ARROWS = {"better": "▲", "similar": "●", "worse": "▼"}

STYLE = Path(__file__).with_name("style.css").read_text(encoding="utf-8")
NUMBERS = re.compile(r"(?<!\w)([+-]?\d+(?:[.,]\d+)*)")


@lru_cache(maxsize=1)
def copybook() -> dict:
    """Load fixed, reviewed copy shared with the decision cards."""
    return read_yaml("copy.yaml")


def labels() -> dict:
    """Return the screen labels."""
    return copybook()["ui"]


def favicon() -> Image.Image:
    """Draw a legible hexagonal outline for the browser tab."""
    icon = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    points = [(16, 3), (28, 10), (28, 22), (16, 29), (4, 22), (4, 10)]
    ImageDraw.Draw(icon).line(points + points[:1], fill=APP_COLOR["basalt"], width=2, joint="curve")
    output = BytesIO()
    icon.save(output, "PNG")
    output.seek(0)
    return Image.open(output)


def text_with_numbers(value: str) -> str:
    """Escape text and style the numbers it already contains."""
    return "".join(f'<span class="b-number">{escape(part)}</span>' if index % 2 else escape(part)
                   for index, part in enumerate(NUMBERS.split(value)))


def header(site_name: str | None = None) -> None:
    """Render the basalt wordmark and theme."""
    logo = (
        '<svg viewBox="0 0 22 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M11 1.1 19.7 5.6v8.8L11 18.9l-8.7-4.5V5.6Z"/></svg>'
    )
    st.markdown(f"<style>{STYLE}</style>", unsafe_allow_html=True)
    wordmark = f'<a class="b-brand" href="?">{logo}<span>{escape(labels()["brand"])}</span></a>'
    location = (f'<div class="b-location"><span class="b-location-name">{text_with_numbers(site_name)}</span>'
                '<a href="?" class="b-change-location">Change location</a></div>') if site_name else ""
    st.markdown(f'<header class="b-masthead">{wordmark}{location}</header>', unsafe_allow_html=True)


def footer() -> None:
    """Show the scope statement on every page."""
    scope = SCOPE.replace("; global", ". The tool uses global")
    st.markdown(f'<footer class="b-v2-footer"><p>{escape(scope)}</p>'
                f'<p>{escape(labels()["local_advice"])}</p></footer>', unsafe_allow_html=True)


def stage_navigation(**params: str | float) -> None:
    """Stage a shareable route from a widget callback."""
    st.session_state["pending_route"] = {name: str(value) for name, value in params.items()}


def goto(**params: str | float) -> None:
    """Update the route after a form returns new values."""
    stage_navigation(**params)
    st.rerun()


def apply_navigation() -> None:
    """Send the selected shareable route to the browser in the fresh render."""
    pending = st.session_state.pop("pending_route", None)
    if pending is not None:
        st.query_params.from_dict(pending)


def how_it_works() -> None:
    """Show the five steps used to compare rotations."""
    ui = labels()
    with st.expander(ui["how_it_works"]):
        st.markdown("\n".join(f"{index}. {step}" for index, step in enumerate(ui["how_steps"], 1)))


def arrow_rows(arrows: dict[str, str]) -> None:
    """Show each comparison direction with its text label."""
    ui = labels()
    rows = []
    for axis in ("soil", "water", "risk"):
        tone = arrows[axis]
        label = f'{ui[axis]}: {ui["tone"][tone].lower()}'
        rows.append(f'<div class="b-arrow" style="color:{APP_COLOR[tone]}">{ARROWS[tone]} {escape(label)}</div>')
    st.markdown("".join(rows), unsafe_allow_html=True)
