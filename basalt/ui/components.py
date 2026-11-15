from functools import lru_cache
from html import escape
from io import BytesIO

import streamlit as st
from PIL import Image, ImageDraw

from basalt.knowledge.loader import read_yaml

APP_COLOR = {
    "basalt": "#24272B", "ash": "#5F656C", "fracture": "#D5D8DB", "paper": "#F7F7F6",
    "plate": "#FFFFFF", "iron": "#A4472A", "better": "#2E6A47", "similar": "#5F656C",
    "worse": "#9B2D2D",
}
ARROWS = {"better": "▲", "similar": "●", "worse": "▼"}

STYLE = """
<style>
@font-face{font-family:'IBM Plex Sans';src:url('./app/static/fonts/IBMPlexSans.ttf') format('truetype');font-weight:100 700;font-display:swap}
@font-face{font-family:'IBM Plex Mono';src:url('./app/static/fonts/IBMPlexMono-Regular.ttf') format('truetype');font-weight:400;font-display:swap}
:root{--basalt:#24272B;--ash:#5F656C;--fracture:#D5D8DB;--plate:#fff;--iron:#A4472A}
.stApp,.stApp button,.stApp input,.stApp select,.stApp textarea{font-family:'IBM Plex Sans',sans-serif}
[data-testid="stHeader"]{display:none}
[data-testid="stAppViewBlockContainer"]{max-width:1328px;padding:32px 40px 48px}
.b-brand{display:flex;align-items:center;gap:8px;font-size:20px;font-weight:600;padding:0 0 16px;border-bottom:1px solid var(--fracture);margin-bottom:16px}
.b-brand svg{width:22px;height:20px}
.stApp h1{font-size:28px;font-weight:600;line-height:1.22;letter-spacing:-.015em;padding:4px 0 8px}
.stApp h2{font-size:20px;font-weight:600;line-height:1.28;letter-spacing:-.01em;padding:8px 0}
.stApp h3{font-size:16px;font-weight:600;line-height:1.32;padding:4px 0}
.stApp p,.stApp li{font-size:16px;line-height:1.5}
.stApp a{color:var(--iron)}
.stApp [data-testid="stCaptionContainer"] p{color:var(--ash);font-size:13px;line-height:1.45}
.stApp [data-testid="stVerticalBlockBorderWrapper"]{border-radius:4px;border-color:var(--fracture);background:var(--plate)}
.stApp button[kind="secondary"],.stApp button[kind="primary"]{border-radius:4px}
.stApp button[kind="secondary"]{background:var(--plate);border-color:var(--fracture)}
.stApp button:focus-visible,.stApp a:focus-visible{outline:2px solid var(--iron);outline-offset:2px}
.stApp [data-testid="stTabs"] button{font-size:16px}
.stApp div[role="tablist"]{margin-bottom:8px}
.stApp .b-hero{max-width:35ch;padding:4px 0 0}
.stApp .b-hero h1{margin:0 0 6px}
.stApp .b-hero p{margin:0}
.stApp .b-chart-legend{display:flex;gap:6px 16px;flex-wrap:wrap;color:var(--ash);font-size:13px;margin-top:-8px}
.stApp .b-legend-mark{display:inline-block;width:12px;height:12px;margin-right:5px;vertical-align:-2px}
.stApp .b-pattern{border-top:1px solid var(--fracture);padding:8px 0;color:var(--basalt)}
.stApp .b-pattern:first-child{border-top:0}
.stApp .b-arrow{font-size:14px;line-height:1.75}
.stApp .b-count,.stApp .b-validation td:nth-child(3){font-family:'IBM Plex Mono',monospace;font-size:.91em}
.stApp .b-verdict{font-weight:500;font-size:15px;line-height:1.45;min-height:62px;margin:0}
.stApp .b-tag{color:var(--ash);font-size:13px}
.stApp .b-practice{margin:4px 0 12px;border-top:1px solid var(--fracture);padding-top:6px;font-size:13px}
.stApp .b-practice-row{margin-top:4px}
.stApp .b-practice-track{height:6px;position:relative}
.stApp .b-practice-track span{height:6px;display:block}
.stApp .b-practice-track i{height:10px;display:block;position:absolute;top:-2px;border-inline:1px solid var(--basalt)}
.stApp .b-validation{width:100%;text-align:left;border-collapse:collapse;background:var(--plate);color:var(--basalt);font-size:14px}
.stApp .b-validation td,.stApp .b-validation th{padding:8px;border:0;border-bottom:1px solid var(--fracture);text-align:left;vertical-align:top}
.stApp .b-validation th{font-weight:600}
.stApp .b-validation-wrap{max-width:100%;overflow-x:auto}
@media(max-width:700px){
 [data-testid="stAppViewBlockContainer"]{padding:20px 16px 32px}
 .b-brand{margin-bottom:8px}
 .stApp .b-hero{max-width:100%}
 .stApp .b-verdict{min-height:0}
 .stApp [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
 .stApp [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{min-width:220px}
}
@media print{
 [data-testid="stAppViewContainer"],[data-testid="stAppViewBlockContainer"]{overflow:visible;height:auto;max-height:none}
 [data-testid="stButton"]{display:none}
 [class*="st-key-slide-"]{break-inside:avoid;break-after:page}
 .st-key-slide-validation{break-after:auto}
}
</style>
"""


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


def header() -> None:
    """Render the Basalt wordmark and theme."""
    logo = (
        '<svg viewBox="0 0 22 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M11 1.1 19.7 5.6v8.8L11 18.9l-8.7-4.5V5.6Z"/></svg>'
    )
    st.markdown(STYLE, unsafe_allow_html=True)
    st.markdown(f'<div class="b-brand">{logo}{escape(labels()["brand"])}</div>', unsafe_allow_html=True)


def goto(**params: str | float) -> None:
    """Update the shareable field URL."""
    st.query_params.from_dict({name: str(value) for name, value in params.items()})
    st.rerun()


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
