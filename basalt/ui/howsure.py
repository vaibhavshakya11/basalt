from html import escape

import streamlit as st

from basalt.ui.components import APP_COLOR, copybook, labels

STATUS_TONES = {"pass": "better", "caveat": "iron", "fail": "worse", "not_run": "similar"}

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
.stApp .b-validation-board .b-check-coverage{color:var(--basalt);max-width:74ch;margin:0 0 12px}
.stApp .b-validation-board .b-check-coverage p{margin:0 0 3px}
.stApp .b-validation-board .b-check-coverage .b-check-notice{font-weight:500;font-size:14px}
.stApp .b-validation-board .b-check-coverage .b-check-absent{font-size:14px;color:var(--ash)}
.stApp .b-check-spotlights{list-style:none;padding:0;margin:0 0 24px}
.stApp .b-validation-board .b-check-spotlight{--check-tone:var(--ash);display:grid;
 grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);
 gap:20px 32px;padding:18px 22px;border:1px solid var(--fracture);border-top:3px solid var(--check-tone);
 background:var(--plate)}
.stApp .b-check-spotlight[data-status="pass"]{--check-tone:var(--green)}
.stApp .b-check-spotlight[data-status="caveat"]{--check-tone:var(--iron)}
.stApp .b-check-spotlight[data-status="fail"]{--check-tone:#9B2D2D}
.stApp .b-check-spotlight h3{font-size:23px;line-height:1.2;margin:3px 0;padding:0}
.stApp .b-check-spotlight p{margin:4px 0 0;font-size:14px;line-height:1.45}
.stApp .b-check-spotlight .b-check-hero-number{font:500 38px/1 'IBM Plex Sans',sans-serif;letter-spacing:-.035em}
.stApp .b-check-spotlight .b-check-number-label{margin-left:8px;font-size:13px;color:var(--ash)}
.stApp .b-check-spotlight .b-check-context{color:var(--basalt)}
.stApp .b-check-spotlight .b-check-note{color:var(--ash);margin-left:0}
.stApp .b-check-spotlight .b-check-status{color:var(--check-tone);font-size:13px}
.stApp .b-validation-board .b-check-group{margin:0 0 22px}
.stApp .b-validation-board .b-check-group h3{font-size:19px}
.stApp .b-validation-board .b-check-list .b-check{padding-block:12px}
.stApp .b-validation-board .b-check-list .b-check[data-status="fail"]{
 border-inline-start:3px solid #9B2D2D;padding-inline-start:11px;background:#9B2D2D08}
.stApp .b-check-guide{border-block:1px solid var(--fracture);padding:4px 0}
.stApp .b-check-guide summary{font-size:16px;font-weight:600;min-height:40px;padding-block:8px}
.stApp .b-check-guide summary:focus-visible{outline:2px solid var(--iron);outline-offset:3px}
.stApp .b-method-section{margin:18px 0;max-width:82ch}
.stApp .b-method-section h3{font-size:17px;margin:0;padding-bottom:3px}
.stApp .b-method-section p,.stApp .b-method-section li,.stApp .b-glossary{font-size:14px}
.stApp .b-method-check{border-top:1px solid var(--fracture);padding:9px 0}
.stApp .b-method-check h4{font-size:14px;margin:0;padding:0}
.stApp .b-method-check p{margin:3px 0}
.stApp .b-method-check .b-check-source{font-size:13px}
@media(max-width:700px){
 .stApp .b-validation-board .b-check-spotlight{grid-template-columns:minmax(0,1fr);padding:14px;gap:8px}
 .stApp .b-check-spotlight h3{font-size:20px}
 .stApp .b-check-spotlight .b-check-hero-number{font-size:32px}
 .stApp .b-validation-board .b-check-list .b-check{gap:4px}
 .stApp .b-validation-board .b-check-list .b-check-note{margin-left:2.9rem}
 .stApp .b-method-check .b-check-source{grid-template-columns:minmax(0,1fr);gap:2px}
 .stApp .b-method-check .b-check-source dd{margin-bottom:5px}
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


def _source_terms(check: dict, ui: dict, measurements: list[tuple[str, str]]) -> str:
    source = " · ".join(str(check[key]) for key in ("dataset", "version", "period") if check.get(key))
    entries = [*measurements, (ui["validation_columns"][3], source), (ui["validation_rule"], check["pass_rule"])]
    if check.get("n") and check["check_id"] not in {"V2", "V7"}:
        entries.append((ui["validation_sample"], f'{check["n"]:,}'))
    terms = "".join(f"<dt>{escape(name)}</dt><dd>{escape(str(value))}</dd>" for name, value in entries if value)
    return f'<dl class="b-check-source">{terms}</dl>'


def _check_row(check: dict, ui: dict, *, include_source: bool) -> str:
    status = check["status"]
    tone = APP_COLOR[STATUS_TONES[status]]
    result, measurements = _prominent_result(check, ui)
    threshold = ""
    if include_source:
        threshold = (f'<details class="b-check-details"><summary>{escape(ui["validation_details"])}</summary>'
                     f'{_source_terms(check, ui, measurements)}</details>')
    if status == "fail" and not include_source:
        threshold = (f'<p class="b-check-note"><strong>{escape(ui["validation_rule"])}</strong> '
                     f'{escape(check["pass_rule"])}</p>')
    return (
        f'<li class="b-check" data-status="{escape(status)}"><div><div class="b-check-heading">'
        f'<span class="b-check-id">{escape(check["check_id"])}</span>'
        f'<span class="b-check-title">{escape(check["metric"])}</span></div>'
        f'<div class="b-check-result"><span class="b-check-status" style="color:{tone}">'
        f'{escape(ui["validation_status"][status])}</span>'
        f'{result}</div></div><div>'
        f'<p class="b-check-note">{escape(check["note"])}</p>{threshold}</div></li>'
    )


def _check_list(checks: list[dict], ui: dict, *, include_source: bool = False) -> str:
    rows = ''.join(_check_row(check, ui, include_source=include_source) for check in checks)
    return f'<ol class="b-check-list">{rows}</ol>'


def _check_group(checks: list[dict], heading: str, ui: dict) -> str:
    return f'<section class="b-check-group"><h3>{escape(heading)}</h3>{_check_list(checks, ui)}</section>' if checks else ""


def _spotlight(check: dict, ui: dict) -> str:
    identifier = check["check_id"]
    status = check["status"]
    value = check["value"]
    if identifier == "V2":
        title = ui["validation_v2_title"]
        note = ui["validation_v2_shared"]
        number = _format_value(value["Arrow agreement (%)"], "%")
        measure = ""
        summary = ui["validation_v2_counts"].format(
            matched=value["Matching arrows"], total=value["Compared arrows"],
            alternatives=value["Matching alternative arrows"], alternative_total=value["Compared alternative arrows"],
        )
    else:
        title = ui["validation_v7_title"]
        note = check["note"]
        number = _format_value(value)
        measure = ui["validation_v7_scale"]
        summary = ui["validation_v7_pairs"].format(n=check["n"])
    return (
        f'<li class="b-check b-check-spotlight" data-status="{escape(status)}"><div>'
        f'<span class="b-check-id">{escape(identifier)}</span><h3>{escape(title)}</h3>'
        f'<span class="b-check-status">{escape(ui["validation_status"][status])}</span>'
        f'<p class="b-check-note">{escape(note)}</p></div><div>'
        f'<strong class="b-check-value b-check-hero-number">{escape(number)}</strong>'
        f'<span class="b-check-number-label">{escape(measure)}</span>'
        f'<p class="b-check-context">{escape(summary)}</p></div></li>'
    )


def _coverage(checks: list[dict], ui: dict) -> str:
    tally = {status: sum(check["status"] == status for check in checks) for status in STATUS_TONES}
    copy = [f'<p>{escape(ui["validation_lead"])}</p>']
    for status, key, css in (("fail", "failed", "b-check-notice"), ("not_run", "unavailable", "b-check-absent")):
        count = tally[status]
        if count:
            number = "one" if count == 1 else "many"
            message = ui[f"validation_{key}_{number}"].format(n=count)
            copy.append(f'<p class="{css}">{escape(message)}</p>')
    completed = {check["check_id"] for check in checks if check["status"] != "not_run"}
    if completed and completed <= {"V1", "V4"}:
        copy.append(f'<p class="b-check-absent">{escape(ui["validation_model_only"])}</p>')
    return f'<div class="b-check-coverage">{"".join(copy)}</div>'


def _dashboard_checks(checks: list[dict], ui: dict) -> str:
    spotlight, caution, passed = [], [], []
    for check in checks:
        if check["status"] == "not_run":
            continue
        identifier, value = check["check_id"], check["value"]
        paired = identifier == "V2" and isinstance(value, dict) and "Arrow agreement (%)" in value
        if paired or identifier == "V7" and value is not None:
            spotlight.append(check)
        elif check["status"] == "pass":
            passed.append(check)
        else:
            caution.append(check)
    body = _coverage(checks, ui)
    if spotlight:
        body += f'<ul class="b-check-spotlights">{"".join(_spotlight(check, ui) for check in spotlight)}</ul>'
    caution.sort(key=lambda check: check["status"] != "fail")
    return body + _check_group(caution, ui["validation_attention"], ui) + _check_group(passed, ui["validation_passes"], ui)


def validation_table(checks: list[dict], *, totals: bool = False) -> None:
    """Show validation results on the field dashboard or the slides."""
    ui = labels()
    if not checks:
        st.caption(ui["validation_empty"])
        return
    markup = _dashboard_checks(checks, ui) if totals else _check_list(checks, ui, include_source=True)
    css = "b-validation b-validation-board" if totals else "b-validation"
    st.markdown(f'{VALIDATION_STYLE}<section class="{css}" aria-label="{escape(ui["validation"])}">'
                f'{markup}</section>', unsafe_allow_html=True)


def _method_check(check: dict, ui: dict) -> str:
    _, measurements = _prominent_result(check, ui)
    return (
        f'<div class="b-method-check"><h4>{escape(check["check_id"])} · {escape(check["metric"])}</h4>'
        f'<p>{escape(ui["validation_status"][check["status"]])}. {escape(check["note"])}</p>'
        f'{_source_terms(check, ui, measurements)}</div>'
    )


def _section(heading: str, content: str) -> str:
    return f'<section class="b-method-section"><h3>{escape(heading)}</h3>{content}</section>'


def _bullets(lines: tuple[str, ...] | list[str], *, ordered: bool = False) -> str:
    tag = "ol" if ordered else "ul"
    return f'<{tag}>' + "".join(f'<li>{escape(line)}</li>' for line in lines) + f'</{tag}>'


def _notes(bundle: dict, ui: dict) -> None:
    assumptions = tuple(dict.fromkeys(line for option in bundle["evidence"] for line in option["assumptions_L"]))
    datasets = tuple(dict.fromkeys(source for option in bundle["evidence"] for source in option["datasets"]))
    glossary = copybook()["glossary"]
    season_start = bundle["field_story"]["site"]["season_year_start"]
    terms = "".join(
        f'<dt>{escape(term)}</dt><dd>{escape(glossary[key].format(season_year_start=season_start))}</dd>'
        for key, term in ui["glossary_terms"].items()
    )
    sections = [
        _section(ui["validation_method_checks"], "".join(_method_check(check, ui) for check in bundle["validation"])),
        _section(ui["limitations"], _bullets(ui["limits"])),
        _section(ui["assumptions"], _bullets(assumptions) if assumptions else f'<p>{escape(ui["no_assumptions"])}</p>'),
        _section(ui["datasets_heading"], f'<p>{escape(ui["datasets_text"])}</p>'),
        _section(ui["satellites_heading"], f'<p>{escape(ui["satellites_text"])}</p>'),
        _section(ui["how_it_works"], _bullets(ui["how_steps"], ordered=True)),
        _section(ui["glossary"], f'<dl class="b-glossary">{terms}</dl>'),
    ]
    if datasets:
        sections.insert(3, _section(ui["datasets_used"], _bullets(datasets)))
    st.markdown(
        f'<details class="b-check-guide"><summary>{escape(ui["validation_guide"])}</summary>'
        f'{"".join(sections)}</details>', unsafe_allow_html=True,
    )


def how_sure(bundle: dict) -> None:
    """Render the visible validation results and a single guide to the methods."""
    ui = labels()
    st.markdown(f'## {ui["validation"]}')
    validation_table(bundle["validation"], totals=True)
    _notes(bundle, ui)
