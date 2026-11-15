from html import escape

import streamlit as st

from basalt.ui.components import APP_COLOR, copybook, how_it_works, labels

STATUS_TONES = {"pass": "better", "caveat": "iron", "fail": "worse", "not_run": "similar"}
MODEL_CHECKS = {"V1", "V4"}

VALIDATION_STYLE = """
<style>
.stApp .b-validation{background:transparent}
.stApp .b-validation .b-check-list{list-style:none;padding:0;margin:0}
.stApp .b-check-group{margin:0 0 20px}
.stApp .b-check-group h3{margin:0;padding:0 0 8px;font-size:16px}
.stApp .b-check-group .b-check-list{border-top:1px solid var(--fracture)}
.stApp .b-check-coverage{margin:0 0 16px;color:var(--ash);overflow-wrap:anywhere}
.stApp .b-check-deferred{border-block:1px solid var(--fracture);padding:10px 0;color:var(--ash)}
.stApp .b-check-deferred>summary{font-weight:600;min-height:34px;padding-block:6px}
.stApp .b-check-deferred>summary:focus-visible{outline:2px solid var(--iron);outline-offset:3px}
.stApp .b-check-deferred .b-check:last-child{border-bottom:0}
.stApp .b-validation .b-check{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);
 gap:16px 24px;margin:0;padding:16px 0;border-bottom:1px solid var(--fracture);min-width:0}
.stApp .b-check-heading{display:grid;grid-template-columns:2.4rem minmax(0,1fr);gap:8px;align-items:baseline}
.stApp .b-check-id{font:400 12px/1.4 'IBM Plex Mono',monospace;color:var(--ash)}
.stApp .b-check-title{font-size:15px;font-weight:600;line-height:1.35}
.stApp .b-check-result{margin:8px 0 0 2.9rem;font-size:14px;display:flex;gap:4px 12px;flex-wrap:wrap}
.stApp .b-check-status{font-weight:600}
.stApp .b-check-value{font:400 13px/1.45 'IBM Plex Mono',monospace;overflow-wrap:anywhere}
.stApp .b-check-headline{font-size:16px;font-weight:600}
.stApp .b-check-result .b-check-context{flex-basis:100%;margin:0;color:var(--ash);line-height:1.4}
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
 .stApp .b-check-note,.stApp .b-check-details{margin-left:0}
}
@media print{
 .stApp .b-validation .b-check{break-inside:avoid;gap:12px;padding-block:7px}
 .stApp .b-check-details,.stApp .b-check-deferred{display:none}
}
</style>
"""


def _format_value(value: float | int | str, unit: str = "", *, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        value = f"{value:.{digits}g}"
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


def _prominent_result(check: dict, ui: dict) -> tuple[str, list[tuple[str, str]]]:
    value = check["value"]
    if check["check_id"] == "V2" and isinstance(value, dict) and "Arrow agreement (%)" in value:
        rate = escape(_format_value(value["Arrow agreement (%)"], "%"))
        line = ui.get("validation_v2_counts", "{matched} of {total} ratings agreed, including {alternatives} of "
                      "{alternative_total} ratings for alternative rotations.").format(
            matched=value["Matching arrows"], total=value["Compared arrows"],
            alternatives=value["Matching alternative arrows"], alternative_total=value["Compared alternative arrows"],
        )
        details = []
        if "Median ET difference (mm/year)" in value:
            details.append((ui.get("validation_water_gap", "Median difference in crop water use"),
                            _format_value(value["Median ET difference (mm/year)"], "mm/year", digits=4)))
        if "Median soil-score difference (points)" in value:
            details.append((ui.get("validation_soil_gap", "Median difference in soil score"),
                            _format_value(value["Median soil-score difference (points)"], "points")))
        return f'<strong class="b-check-value b-check-headline">{rate}</strong><p class="b-check-context">{escape(line)}</p>', details
    if check["check_id"] == "V7" and value is not None:
        result = escape(f'Spearman r = {_format_value(value)}')
        text = ui.get("validation_v7_pairs", "Both sources had values for {n:,} days.").format(n=check["n"])
        return (f'<strong class="b-check-value b-check-headline">{result}</strong>'
                f'<p class="b-check-context">{escape(text)}</p>'), []
    return _result_values(value, check["unit"]), []


def _source_details(check: dict, ui: dict, measurements: list[tuple[str, str]]) -> str:
    source = " · ".join(str(check[key]) for key in ("dataset", "version", "period") if check.get(key))
    entries = [*measurements, (ui["validation_columns"][3], source), (ui["validation_rule"], check["pass_rule"])]
    if check.get("n") and check["check_id"] not in {"V2", "V7"}:
        entries.append((ui["validation_sample"], f'{check["n"]:,}'))
    terms = "".join(f"<dt>{escape(name)}</dt><dd>{escape(str(value))}</dd>" for name, value in entries if value)
    detail_label = escape(ui["validation_details"])
    return (f'<details class="b-check-details"><summary>{detail_label}</summary>'
            f'<dl class="b-check-source">{terms}</dl></details>')


def _check_row(check: dict, ui: dict) -> str:
    status = check["status"]
    tone = APP_COLOR[STATUS_TONES[status]]
    result, measurements = _prominent_result(check, ui)
    return (
        '<li class="b-check"><div><div class="b-check-heading">'
        f'<span class="b-check-id">{escape(check["check_id"])}</span>'
        f'<span class="b-check-title">{escape(check["metric"])}</span></div>'
        f'<div class="b-check-result"><span class="b-check-status" style="color:{tone}">'
        f'{escape(ui["validation_status"][status])}</span>'
        f'{result}</div></div><div>'
        f'<p class="b-check-note">{escape(check["note"])}</p>{_source_details(check, ui, measurements)}</div></li>'
    )


def _check_list(checks: list[dict], ui: dict) -> str:
    return f'<ol class="b-check-list">{"".join(_check_row(check, ui) for check in checks)}</ol>'


def _check_group(checks: list[dict], heading: str, ui: dict) -> str:
    return f'<section class="b-check-group"><h3>{escape(heading)}</h3>{_check_list(checks, ui)}</section>' if checks else ""


def _dashboard_checks(checks: list[dict], ui: dict) -> str:
    model, local, deferred = [], [], []
    for check in checks:
        if check["status"] == "not_run":
            deferred.append(check)
        elif check["check_id"] in MODEL_CHECKS:
            model.append(check)
        else:
            local.append(check)
    context = ""
    if model and not local:
        text = ui.get("validation_model_only", "The results here cover the model calculations. "
                      "Local comparisons need supporting data for this location.")
        context = f'<p class="b-check-coverage">{escape(text)}</p>'
    body = (context + _check_group(local, ui.get("validation_local", "Local comparisons"), ui)
            + _check_group(model, ui.get("validation_model", "Model checks"), ui))
    if deferred:
        heading = ui.get("validation_deferred", "Checks without results ({n})").format(n=len(deferred))
        body += (f'<details class="b-check-deferred"><summary>{escape(heading)}</summary>'
                 f'{_check_list(deferred, ui)}</details>')
    return body


def validation_table(checks: list[dict], *, totals: bool = False) -> None:
    """Show check results and keep unavailable checks accessible on the field dashboard."""
    ui = labels()
    if not checks:
        st.caption(ui["validation_empty"])
        return
    markup = _dashboard_checks(checks, ui) if totals else _check_list(checks, ui)
    st.markdown(f'{VALIDATION_STYLE}<section class="b-validation" aria-label="{escape(ui["validation"])}">'
                f'{markup}</section>', unsafe_allow_html=True)


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
