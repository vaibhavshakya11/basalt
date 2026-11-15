from html import escape

import streamlit as st

from basalt.ui.components import APP_COLOR, copybook, how_it_works, labels

STATUS_TONES = {"pass": "better", "caveat": "similar", "fail": "worse", "not_run": "similar"}


def _format_value(value, unit: str) -> str:
    if value is None:
        return "·"
    if isinstance(value, dict):
        return " · ".join(f"{key.replace('_', ' ')} {_format_value(number, '')}" for key, number in value.items())
    return f"{value:.3g} {unit}".strip() if isinstance(value, (float, int)) else f"{value} {unit}".strip()


def validation_table(checks: list[dict]) -> None:
    ui = labels()
    headings = "".join(f"<th scope='col'>{escape(label)}</th>" for label in ui["validation_columns"])
    rows = []
    for check in checks:
        tone = APP_COLOR[STATUS_TONES[check["status"]]]
        columns = (
            check["check_id"], ui["validation_status"][check["status"]],
            _format_value(check["value"], check["unit"]), check["dataset"], check["note"],
        )
        styles = ("", f"color:{tone};font-weight:600", "", "", "")
        cells = "".join(f'<td style="{style}">{escape(str(value))}</td>'
                        for value, style in zip(columns, styles, strict=True))
        rows.append(f"<tr>{cells}</tr>")
    st.markdown(f'<div class="b-validation-wrap"><table class="b-validation"><thead><tr>{headings}</tr>'
                f'</thead><tbody>{"".join(rows)}</tbody></table></div>', unsafe_allow_html=True)


def _glossary(season_start: str) -> None:
    ui = labels()
    definitions = copybook()["glossary"]
    with st.expander(ui["glossary"]):
        terms = ui["glossary_terms"]
        key = st.selectbox(ui["glossary"], list(terms), format_func=terms.__getitem__, label_visibility="collapsed")
        st.write(definitions[key].format(season_year_start=season_start))


def how_sure(bundle: dict) -> None:
    """Render validation, assumptions and the documented method limits."""
    ui = labels()
    st.subheader(ui["tab_sure"])
    st.markdown(f'### {ui["validation"]}')
    validation_table(bundle["validation"])
    st.subheader(ui["assumptions"])
    assumptions = dict.fromkeys(line for option in bundle["evidence"] for line in option["assumptions_L"])
    for assumption in assumptions:
        st.write(f"- {assumption}")
    if not assumptions:
        st.caption(ui["no_assumptions"])
    st.subheader(ui["satellites_heading"])
    st.write(ui["satellites_text"])
    st.subheader(ui["datasets_heading"])
    st.write(ui["datasets_text"])
    st.subheader(ui["limitations"])
    for limitation in ui["limits"]:
        st.write(f"- {limitation}")
    _glossary(bundle["field_story"]["site"]["season_year_start"])
    how_it_works()
