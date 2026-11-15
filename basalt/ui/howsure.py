from collections import Counter
from html import escape

import streamlit as st

from basalt.ui.components import APP_COLOR, copybook, how_it_works, labels

STATUS_TONES = {"pass": "better", "caveat": "iron", "fail": "worse", "not_run": "similar"}

VALIDATION_STYLE = """
<style>
.stApp .b-validation{background:transparent;border-top:1px solid var(--fracture)}
.stApp .b-validation .b-check-list{list-style:none;padding:0;margin:0}
.stApp .b-check-totals{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0 0 12px}
.stApp .b-check-total{padding:8px 12px;border-left:1px solid var(--fracture);min-width:0}
.stApp .b-check-total:first-child{border-left:0;padding-left:0}
.stApp .b-check-total strong{display:block;font:400 20px/1.2 'IBM Plex Mono',monospace}
.stApp .b-check-total span{font-size:13px;color:var(--ash)}
.stApp .b-validation .b-check{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);
 gap:16px 24px;margin:0;padding:16px 0;border-bottom:1px solid var(--fracture);min-width:0}
.stApp .b-check-heading{display:grid;grid-template-columns:2.4rem minmax(0,1fr);gap:8px;align-items:baseline}
.stApp .b-check-id{font:400 12px/1.4 'IBM Plex Mono',monospace;color:var(--ash)}
.stApp .b-check-title{font-size:15px;font-weight:600;line-height:1.35}
.stApp .b-check-result{margin:8px 0 0 2.9rem;font-size:14px;display:flex;gap:4px 12px;flex-wrap:wrap}
.stApp .b-check-status{font-weight:600}
.stApp .b-check-value{font:400 13px/1.45 'IBM Plex Mono',monospace;overflow-wrap:anywhere}
.stApp .b-check-values{display:grid;flex-basis:100%;gap:4px 12px;margin:4px 0 0}
.stApp .b-check-values div{display:flex;align-items:baseline;gap:6px 12px;flex-wrap:wrap}
.stApp .b-check-values dt{font-size:13px;color:var(--ash)}
.stApp .b-check-values dd{margin:0}
.stApp .b-check-note{font-size:14px;line-height:1.45;margin:0 0 4px;overflow-wrap:anywhere}
.stApp .b-check-details{margin:3px 0 0;color:var(--ash);font-size:13px}
.stApp .b-check-details summary{width:fit-content;color:var(--iron);padding-block:3px}
.stApp .b-check-details summary:focus-visible{outline:2px solid var(--iron);outline-offset:3px}
.stApp .b-check-source{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 10px;margin:5px 0 0}
.stApp .b-check-source dt{font-weight:600}
.stApp .b-check-source dd{margin:0;overflow-wrap:anywhere}
.stApp .b-glossary{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:8px 16px;margin:0}
.stApp .b-glossary dt{font-weight:600}
.stApp .b-glossary dd{margin:0}
@media(max-width:700px){
 .stApp .b-validation .b-check{grid-template-columns:minmax(0,1fr);gap:8px;padding-block:12px}
 .stApp .b-check-note,.stApp .b-check-details{margin-left:2.9rem}
 .stApp .b-glossary{grid-template-columns:minmax(0,1fr);gap:4px}
 .stApp .b-glossary dd{margin-bottom:8px}
}
@media(max-width:380px){
 .stApp .b-check-total{padding-inline:8px}
 .stApp .b-check-total span{font-size:12px}
 .stApp .b-check-note,.stApp .b-check-details{margin-left:0}
}
@media print{
 .stApp .b-validation .b-check{break-inside:avoid;gap:12px;padding-block:7px}
 .stApp .b-check-details{display:none}
}
</style>
"""


def _format_value(value: float | int | str, unit: str = "") -> str:
    if isinstance(value, (int, float)):
        value = f"{value:.3g}"
    if unit == "%":
        return f"{value}%"
    return f"{value} {unit}".strip()


def _result_values(value, unit: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, dict):
        return f'<span class="b-check-value">{escape(_format_value(value, unit))}</span>'
    measurements = "".join(
        f'<div><dt>{escape(name.replace("_", " "))}</dt>'
        f'<dd class="b-check-value">{escape(_format_value(number))}</dd></div>'
        for name, number in value.items()
    )
    return f'<dl class="b-check-values">{measurements}</dl>'


def _source_details(check: dict, ui: dict) -> str:
    source = " · ".join(str(check[key]) for key in ("dataset", "version", "period") if check.get(key))
    entries = [(ui["validation_columns"][3], source), (ui["validation_rule"], check["pass_rule"])]
    if check.get("n"):
        entries.append((ui["validation_sample"], f'{check["n"]:,}'))
    terms = "".join(f"<dt>{escape(name)}</dt><dd>{escape(str(value))}</dd>" for name, value in entries if value)
    detail_label = escape(ui["validation_details"])
    return (f'<details class="b-check-details"><summary>{detail_label}</summary>'
            f'<dl class="b-check-source">{terms}</dl></details>')


def _check_row(check: dict, ui: dict) -> str:
    status = check["status"]
    tone = APP_COLOR[STATUS_TONES[status]]
    return (
        '<li class="b-check"><div><div class="b-check-heading">'
        f'<span class="b-check-id">{escape(check["check_id"])}</span>'
        f'<span class="b-check-title">{escape(check["metric"])}</span></div>'
        f'<div class="b-check-result"><span class="b-check-status" style="color:{tone}">'
        f'{escape(ui["validation_status"][status])}</span>'
        f'{_result_values(check["value"], check["unit"])}</div></div><div>'
        f'<p class="b-check-note">{escape(check["note"])}</p>{_source_details(check, ui)}</div></li>'
    )


def validation_table(checks: list[dict], *, totals: bool = False) -> None:
    """Show each check, its result, and the rule used."""
    ui = labels()
    if not checks:
        st.caption(ui["validation_empty"])
        return
    counts = Counter(check["status"] for check in checks)
    tally = "".join(
        f'<div class="b-check-total"><strong style="color:{APP_COLOR[tone]}">{counts[status]}</strong>'
        f'<span>{escape(ui["validation_status"][status])}</span></div>'
        for status, tone in STATUS_TONES.items()
    ) if totals else ""
    prefix = f'<div class="b-check-totals">{tally}</div>' if tally else ""
    checks_markup = "".join(_check_row(check, ui) for check in checks)
    st.markdown(f'{VALIDATION_STYLE}{prefix}<section class="b-validation" aria-label="{escape(ui["validation"])}">'
                f'<ol class="b-check-list">{checks_markup}</ol></section>', unsafe_allow_html=True)


def _glossary(season_start: str) -> None:
    ui = labels()
    definitions = copybook()["glossary"]
    with st.expander(ui["glossary"]):
        terms = "".join(
            f'<dt>{escape(term)}</dt><dd>{escape(definitions[key].format(season_year_start=season_start))}</dd>'
            for key, term in ui["glossary_terms"].items()
        )
        st.markdown(f'<dl class="b-glossary">{terms}</dl>', unsafe_allow_html=True)


def _notes(bundle: dict, ui: dict) -> None:
    assumptions = tuple(dict.fromkeys(line for option in bundle["evidence"] for line in option["assumptions_L"]))
    datasets = tuple(dict.fromkeys(source for option in bundle["evidence"] for source in option["datasets"]))
    with st.expander(ui["limitations"]):
        st.markdown("\n".join(f"- {limitation}" for limitation in ui["limits"]))
    with st.expander(ui["assumptions"]):
        if assumptions:
            st.markdown("\n".join(f"- {assumption}" for assumption in assumptions))
        else:
            st.caption(ui["no_assumptions"])
    with st.expander(ui["datasets_heading"]):
        if datasets:
            st.markdown(f'**{ui["datasets_used"]}**')
            st.markdown("\n".join(f"- {dataset}" for dataset in datasets))
        st.write(ui["datasets_text"])
        st.markdown(f'**{ui["satellites_heading"]}**')
        st.write(ui["satellites_text"])
    _glossary(bundle["field_story"]["site"]["season_year_start"])
    how_it_works()


def how_sure(bundle: dict) -> None:
    """Render validation and keep supporting method information within reach."""
    ui = labels()
    st.markdown(f'## {ui["validation"]}')
    validation_table(bundle["validation"], totals=True)
    _notes(bundle, ui)
