from html import escape

import streamlit as st

from basalt.config import SCOPE
from basalt.ui.components import APP_COLOR, ARROWS, goto, labels
from basalt.ui.howsure import validation_table
from basalt.ui.strata import draw_strata


def _comparison(bundle: dict, site_id: str) -> None:
    ui = labels()
    story = bundle["field_story"]
    st.subheader(story["site"]["name"])
    st.caption(ui[story["tier"]])
    columns = "".join(f"<th scope='col'>{escape(name)}</th>" for name in ui["slide_comparison_columns"])
    summary = []
    for option in bundle["evidence"]:
        cells = []
        for axis in ("soil", "water", "risk"):
            tone = option["arrows"][axis]
            arrow = f'<td style="color:{APP_COLOR[tone]}">{ARROWS[tone]} {escape(ui["tone"][tone])}</td>'
            cells.append(arrow)
        name = escape(option["name"])
        verdict = escape(option["verdict"])
        summary.append(f'<tr><td><strong>{name}</strong><br>{verdict}</td>{"".join(cells)}</tr>')
    st.markdown(f'<div class="b-validation-wrap"><table class="b-validation"><thead><tr>{columns}</tr></thead>'
                f'<tbody>{"".join(summary)}</tbody></table></div>', unsafe_allow_html=True)
    for rejection in bundle["rejections"]:
        description = f'{ui["lever"][rejection["lever"]]}: {rejection["reason"]}'
        st.caption(description)
    if st.button(ui["slides_demos"], key=f"slides-{site_id}"):
        goto(site=site_id)


def slides_view(ludhiana: dict, malawi: dict) -> None:
    """Show five printable pages sourced from the two demo bundles."""
    ui = labels()
    if st.button(ui["try_other_site"], key="slides-home"):
        goto()
    with st.container(key="slide-overview"):
        st.title(ui["page_title"])
        st.write(ui["page_intro"])
        current = ludhiana["field_story"]["current_rotation_id"]
        draw_strata(ludhiana["strata"][current], key="slides-strata")
        st.caption(ui["hero_caption"])
    with st.container(key="slide-method"):
        st.subheader(ui["slides_method"])
        st.markdown("\n".join(f"{ordinal}. {step}" for ordinal, step in enumerate(ui["how_steps"], 1)))
        st.caption(SCOPE)
    for site_id, demo in (("ludhiana", ludhiana), ("malawi", malawi)):
        with st.container(key=f"slide-{site_id}"):
            _comparison(demo, site_id)
    with st.container(key="slide-validation"):
        st.subheader(ui["slides_checks"])
        for demo in (ludhiana, malawi):
            st.markdown(f'**{demo["field_story"]["site"]["name"]}**')
            validation_table([check for check in demo["validation"] if check["check_id"] in {"V1", "V2", "V3"}])
        st.caption(ui["local_advice"])
