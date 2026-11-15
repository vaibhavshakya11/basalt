from html import escape

import streamlit as st

from basalt.config import DEMO_COORDS, SCOPE
from basalt.ui.components import APP_COLOR, ARROWS, goto, labels
from basalt.ui.howsure import validation_table
from basalt.ui.strata import draw_strata

SLIDES_STYLE = """
<style>
.stApp [class*="st-key-slide-"]{padding:12px 0 24px;border-top:1px solid var(--fracture)}
.stApp .st-key-slide-overview{border-top:0;padding-top:0}
.stApp .st-key-slide-overview p{max-width:65ch}
.stApp .st-key-slide-method{max-width:76ch}
.stApp .b-brief-steps{list-style:none;counter-reset:method;display:grid;margin:0;padding:0}
.stApp .b-brief-steps li{border-top:1px solid var(--fracture);padding:12px 0;
 display:grid;grid-template-columns:2.125rem minmax(0,1fr);gap:8px;counter-increment:method}
.stApp .b-brief-steps li::before{content:counter(method);font:400 14px/1.65 'IBM Plex Mono',monospace;color:var(--ash)}
.stApp .b-brief-compare{border-top:1px solid var(--fracture)}
.stApp .b-brief-option{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);
 gap:8px 24px;align-items:center;padding:14px 0;border-bottom:1px solid var(--fracture)}
.stApp .b-brief-baseline{grid-template-columns:minmax(0,1fr)}
.stApp .b-brief-option h3{margin:0;padding:0;font-size:16px;overflow-wrap:anywhere}
.stApp .b-brief-option p{margin:4px 0 0;color:var(--ash);font-size:14px;line-height:1.42}
.stApp .b-brief-current{font-size:13px;font-weight:400;margin-left:8px;color:var(--ash);display:inline-block}
.stApp .b-brief-arrows{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0;font-size:13px}
.stApp .b-brief-arrows dt{color:var(--ash);font-size:12px;line-height:1.25}
.stApp .b-brief-arrows dd{margin:3px 0 0;font-weight:600}
.stApp .b-brief-arrow-symbol{margin-right:3px}
@media(max-width:700px){
 .stApp .b-brief-option{grid-template-columns:minmax(0,1fr);padding-block:12px}
 .stApp .b-brief-arrows{gap:4px;padding-top:3px}
}
@media print{
 .stApp [class*="st-key-slide-"]{break-inside:avoid;padding:0;border:0}
 .stApp .b-brief-option{break-inside:avoid;padding-block:8px}
}
</style>
"""


def _arrows(option: dict, ui: dict) -> str:
    lines = []
    for axis in ("soil", "water", "risk"):
        tone = option["arrows"][axis]
        lines.append(
            f'<div><dt>{escape(ui[axis])}</dt><dd style="color:{APP_COLOR[tone]}">'
            f'<span class="b-brief-arrow-symbol" aria-hidden="true">{ARROWS[tone]}</span>'
            f'{escape(ui["tone"][tone])}</dd></div>'
        )
    return f'<dl class="b-brief-arrows">{"".join(lines)}</dl>'


def _rotation_rows(options: list[dict], ui: dict) -> str:
    rows = []
    for option in options:
        current = option["is_current"]
        qualifier = f'<span class="b-brief-current">{escape(ui["slide_current"])}</span>' if current else ""
        direction = "" if current else _arrows(option, ui)
        row_class = " b-brief-baseline" if current else ""
        rows.append(f'<article class="b-brief-option{row_class}"><div>'
                    f'<h3>{escape(option["name"])}{qualifier}</h3>'
                    f'<p>{escape(option["verdict"])}</p></div>{direction}</article>')
    return f'<div class="b-brief-compare">{"".join(rows)}</div>'


def _comparison(bundle: dict, site_id: str) -> None:
    ui = labels()
    story = bundle["field_story"]
    st.subheader(story["site"]["name"])
    st.caption(ui[story["tier"]])
    st.markdown(_rotation_rows(bundle["evidence"], ui), unsafe_allow_html=True)
    if bundle["rejections"]:
        with st.expander(ui["no_more"]):
            st.markdown("\n".join(
                f'- **{ui["lever"][row["lever"]]}** · {row["reason"]}' for row in bundle["rejections"]
            ))
    if st.button(ui["slides_demos"], key=f"slides-{site_id}"):
        goto(site=site_id)


def slides_view(ludhiana: dict | None, malawi: dict | None) -> None:
    """Show the printable overview, methods, site comparisons and checks."""
    ui = labels()
    sites = (("ludhiana", ludhiana), ("malawi", malawi))
    st.markdown(SLIDES_STYLE, unsafe_allow_html=True)
    if st.button(ui["slide_page_home"], key="slides-home"):
        goto()
    with st.container(key="slide-overview"):
        st.title(ui["page_title"])
        st.write(ui["page_intro"])
        if ludhiana:
            current = ludhiana["field_story"]["current_rotation_id"]
            draw_strata(ludhiana["strata"][current], key="slides-strata")
            st.caption(ui["hero_caption"])
    with st.container(key="slide-method"):
        st.subheader(ui["slides_method"])
        steps = "".join(f"<li>{escape(step)}</li>" for step in ui["how_steps"])
        st.markdown(f'<ol class="b-brief-steps">{steps}</ol>', unsafe_allow_html=True)
        st.caption(SCOPE)
    for site_id, demo in sites:
        with st.container(key=f"slide-{site_id}"):
            if demo:
                _comparison(demo, site_id)
            else:
                st.subheader(DEMO_COORDS[site_id][0])
                st.caption(ui["slide_data_missing"])
    with st.container(key="slide-validation"):
        st.subheader(ui["slides_checks"])
        for _, demo in sites:
            if demo:
                st.markdown(f'### {demo["field_story"]["site"]["name"]}')
                validation_table([check for check in demo["validation"] if check["check_id"] in {"V1", "V2", "V3"}])
        st.caption(ui["local_advice"])
