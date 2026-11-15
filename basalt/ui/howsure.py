import re
from collections import Counter
from html import escape

import streamlit as st

from basalt.ui.components import labels


STATUS_MARKS = {"pass": "▲", "caveat": "●", "fail": "▼", "not_run": "●"}
NUMBERS_IN_TEXT = re.compile(r"(?<!\w)[+\u2212-]?\d+(?:,\d{3})*(?:\.\d+)?(?!\w)")
CHECK_PURPOSE = {
    "V1": "Does the reference water-use calculation match the published FAO example?",
    "V2": "Do global and Punjab crop parameters produce the same rotation ratings?",
    "V3": "How close are the crop calendar dates to the dates estimated from satellite greenness?",
    "V4": "Does the model account for water added, lost or stored each day?",
    "V5": "What share of detected fires fall around the gap between rice and wheat?",
    "V6": "Do rice reference water use and wheat watering frequency fit published Punjab ranges?",
    "V7": "Do the model and SMAP agree on which days were wetter or drier than usual?",
    "V8": "How far is modelled seasonal water use from the satellite estimate?",
}
FAILURE_REASON = {
    "V1": "The computed value fell outside the published example’s tolerance.",
    "V2": "The two sets of ratings disagreed too often to pass.",
    "V3": "The typical difference between dates exceeded the caveat threshold.",
    "V4": "The largest daily difference exceeded the water-balance tolerance.",
    "V6": "At least one of the two medians fell outside its published range.",
    "V7": "The agreement on wetter and drier days fell below the caveat threshold.",
}
DATASET_SOURCES = {
    "NASA POWER": ("About 50 km", "Daily", "Weather and reference water use"),
    "PAU": ("Punjab", "Crop calendar", "Local planting and harvest dates"),
    "GGCMI": ("0.5°", "Crop calendar", "Regional planting and harvest dates"),
    "SoilGrids": ("250 m", "Soil depth layers", "Estimated field soil texture"),
    "MODIS MOD13Q1": ("250 m", "16 days", "Crop calendar and greenness checks"),
    "MODIS MOD16A2GF": ("500 m", "8 days", "Seasonal crop water-use check"),
    "GRACE": ("About 300 km", "Monthly", "Regional water storage trend"),
    "NASA FIRMS": ("375 m", "Satellite overpasses", "Fire timing near the rice harvest"),
    "NASA SMAP": ("9 km", "3 hours", "Root-zone wetness check"),
}

VALIDATION_STYLE = """
<style>
.stApp .b-assurance{min-width:0;width:100%;color:var(--basalt)}
.stApp .b-assurance .b-assurance-context{margin:8px 0 0;max-width:70ch;color:var(--ash)}
.stApp .b-assurance h2{margin:0 0 12px;padding:0}
.stApp .b-assurance section{min-width:0}
.stApp .b-assurance .b-assurance-primary{margin-top:24px}
.stApp .b-assurance .b-assurance-split{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
 gap:32px 48px}
.stApp .b-assurance .b-assurance-split>section{min-width:0}
.stApp .b-assurance .b-assurance-split ul{margin:0;padding-inline-start:20px}
.stApp .b-assurance .b-assurance-split li{margin:0 0 8px;max-width:70ch}
.stApp .b-assurance .b-assurance-methods{margin:0;max-width:70ch}
.stApp .b-assurance.b-validation,.stApp .b-assurance .b-validation{background:transparent}
.stApp .b-assurance-table{margin:0;background:var(--plate);font-size:16px}
.stApp .b-assurance-table th,.stApp .b-assurance-table td{overflow-wrap:anywhere}
.stApp .b-assurance-table tbody th{font-weight:600}
.stApp .b-assurance .b-assurance-checks td:nth-child(3){font:inherit}
.stApp .b-assurance-table .b-assurance-id,.stApp .b-assurance-table .b-assurance-muted{
 color:var(--ash);font-size:var(--type-xs)}
.stApp .b-assurance-table .b-assurance-id{display:block;margin-bottom:4px}
.stApp .b-assurance-table .b-assurance-result,.stApp .b-assurance-table .b-assurance-coverage{
 display:block;margin:0 0 4px}
.stApp .b-assurance-table .b-assurance-secondary{display:block;margin:8px 0 0}
.stApp .b-assurance-table .b-assurance-measure{display:block;margin:0 0 8px}
.stApp .b-assurance-table .b-assurance-status{display:inline-flex;gap:6px;align-items:baseline;
 font-size:14px;font-weight:600;white-space:nowrap;color:var(--ash)}
.stApp .b-assurance-table [data-status="pass"] .b-assurance-status{color:var(--green)}
.stApp .b-assurance-table [data-status="caveat"] .b-assurance-status{color:var(--iron)}
.stApp .b-assurance-table [data-status="fail"] .b-assurance-status{color:var(--red)}
.stApp .b-assurance-table .b-assurance-mobile-label{display:none}
.stApp .b-assurance-checks col:nth-child(1){width:18%}
.stApp .b-assurance-checks col:nth-child(2){width:32%}
.stApp .b-assurance-checks col:nth-child(3){width:20%}
.stApp .b-assurance-checks col:nth-child(4){width:10%}
.stApp .b-assurance-checks col:nth-child(5){width:20%}
.stApp .b-assurance-data col:nth-child(1){width:30%}
.stApp .b-assurance-data col:nth-child(2),.stApp .b-assurance-data col:nth-child(3){width:15%}
.stApp .b-assurance-data col:nth-child(4){width:40%}
@media(max-width:767px){
 .stApp .b-assurance .b-assurance-split{display:block}
 .stApp .b-assurance section{margin-top:40px}
 .stApp .b-assurance-table,.stApp .b-assurance-table tbody{display:block;width:100%}
 .stApp .b-assurance-table{background:transparent}
 .stApp .b-assurance-table colgroup{display:none}
 .stApp .b-assurance-table thead{position:absolute;inline-size:1px;block-size:1px;
  overflow:hidden;clip-path:inset(50%);white-space:nowrap}
 .stApp .b-assurance-table tr{display:grid;grid-template-columns:minmax(0,1fr);
  border-bottom:1px solid var(--fracture);padding:12px 0;gap:8px}
 .stApp .b-assurance-table tr:first-child{border-top:1px solid var(--fracture)}
 .stApp .b-assurance-table th[scope],.stApp .b-assurance-table td[role]{display:block;min-width:0;padding:0;border:0}
 .stApp .b-assurance-table td[role]{display:grid;grid-template-columns:85px minmax(0,1fr);gap:8px 12px}
 .stApp .b-assurance-table .b-assurance-mobile-label{display:block;color:var(--ash);font-size:13px}
 .stApp .b-assurance-table .b-assurance-id{display:inline;margin-right:6px}
 .stApp .b-assurance-table .b-assurance-status{white-space:normal}
}
@media print{
 .stApp .b-assurance-table tr{break-inside:avoid}
}
</style>
"""


def _number(value: float | int) -> str:
    if isinstance(value, int) or value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.4g}"


def _quantity(value: float | int, unit: str = "") -> str:
    if unit == "Spearman r":
        return f'Spearman r = <span class="b-check-value b-number">{_number(value)}</span>'
    suffix = f'<span class="b-assurance-muted"> {escape(unit)}</span>' if unit else ""
    return f'<span class="b-check-value b-number">{_number(value)}</span>{suffix}'


def _prose(text: str) -> str:
    return NUMBERS_IN_TEXT.sub(r'<span class="b-number">\g<0></span>', escape(text))


def _paragraph(text: str, *, muted: bool = False) -> str:
    style = ' class="b-assurance-secondary b-assurance-muted"' if muted else ' class="b-assurance-secondary"'
    return f'<p{style}>{_prose(text)}</p>' if text else ""


def _result(check: dict, ui: dict) -> str:
    value = check["value"]
    identifier = check["check_id"]
    if value is None:
        return "Unavailable"
    if identifier == "V2":
        count = ui["validation_v2_counts"].format(
            matched=f'{value["Matching arrows"]:,}', total=f'{value["Compared arrows"]:,}',
            alternatives=f'{value["Matching alternative arrows"]:,}',
            alternative_total=f'{value["Compared alternative arrows"]:,}',
        )
        result = _quantity(value["Arrow agreement (%)"], "%")
        details = (
            (ui["validation_water_gap"], value.get("Median ET difference (mm/year)"), "mm/year"),
            (ui["validation_soil_gap"], value.get("Median soil-score difference (points)"), "points"),
        )
        return (
            f'<strong class="b-assurance-result">{result}</strong>'
            f'<span class="b-assurance-coverage">{_prose(count)}</span>'
            + "".join(_measure(name, number, unit) for name, number, unit in details if number is not None)
        )
    if isinstance(value, dict):
        return "".join(_measure(name, number) for name, number in value.items())
    result = f'<strong class="b-assurance-result">{_quantity(value, check["unit"])}</strong>'
    if identifier == "V7":
        result += f'<span class="b-assurance-coverage">{_prose(ui["validation_v7_pairs"].format(n=check["n"]))}</span>'
    return result


def _measure(name: str, number: float | int, unit: str = "") -> str:
    return (
        f'<span class="b-assurance-measure"><span class="b-assurance-muted">{escape(name)}</span>'
        f'<br>{_quantity(number, unit)}</span>'
    )


def _cell(heading: str, body: str) -> str:
    return (
        '<td role="cell"><span class="b-assurance-mobile-label" aria-hidden="true">'
        f'{escape(heading)}</span><div>{body}</div></td>'
    )


def _table(headings: tuple[str, ...], rows: str, css: str, label: str) -> str:
    header = "".join(f'<th scope="col" role="columnheader">{escape(heading)}</th>' for heading in headings)
    columns = "<col>" * len(headings)
    return (
        f'<table class="b-v2-table b-assurance-table {css}" aria-label="{escape(label)}" role="table">'
        f'<colgroup>{columns}</colgroup><thead role="rowgroup"><tr role="row">{header}</tr></thead>'
        f'<tbody role="rowgroup">{rows}</tbody></table>'
    )


def _validation_markup(checks: list[dict], ui: dict) -> str:
    headings = ("Check", "What it tests", "Result", "Status", "Data")
    rows = []
    for check in checks:
        status = check["status"]
        identifier = check["check_id"]
        explanation = CHECK_PURPOSE.get(identifier, check["metric"])
        note = check["note"] if identifier not in {"V1", "V4"} or status != "pass" else ""
        if status == "fail" and identifier in FAILURE_REASON:
            note = f"{FAILURE_REASON[identifier]} {note}"
        threshold = _paragraph(f'{ui["validation_rule"]}. {check["pass_rule"]}', muted=True) if status in {"fail", "caveat"} else ""
        status_text = (
            f'<span class="b-assurance-status"><span aria-hidden="true">{STATUS_MARKS[status]}</span>'
            f'{escape(ui["validation_status"][status])}</span>'
        )
        details = " · ".join(check[field] for field in ("version", "period") if check.get(field))
        data = escape(check["dataset"])
        if details:
            data += f'<br><span class="b-assurance-muted b-number">{escape(details)}</span>'
        if check["n"] and identifier not in {"V2", "V7"}:
            data += (
                f'<span class="b-assurance-secondary b-assurance-muted">{escape(ui["validation_sample"])} '
                f'<span class="b-check-value b-number">{check["n"]:,}</span></span>'
            )
        cells = (escape(explanation) + _paragraph(note) + threshold, _result(check, ui), status_text, data)
        rows.append(
            f'<tr class="b-check" role="row" data-status="{status}"><th scope="row" role="rowheader">'
            f'<span class="b-assurance-id b-number">{escape(identifier)}</span>{escape(check["metric"])}</th>'
            + "".join(_cell(heading, content) for heading, content in zip(headings[1:], cells, strict=True))
            + "</tr>"
        )
    return _table(headings, "".join(rows), "b-assurance-checks", ui["validation"])


def _tally(checks: list[dict], ui: dict) -> str:
    counts = Counter(check["status"] for check in checks)
    p, c, f, u = (f'<span class="b-check-value b-number">{counts[status]}</span>' for status in STATUS_MARKS)
    n = f'<span class="b-check-value b-number">{len(checks)}</span>'
    caveats = "has a caveat" if counts["caveat"] == 1 else "have caveats"
    summary = f"{p} of {n} checks passed. {c} {caveats} and {f} failed. Each is explained below."
    coverage = ""
    if counts["not_run"]:
        ending = "check had no result" if counts["not_run"] == 1 else "checks had no result"
        coverage = f'<p class="b-assurance-context">{u} {ending} for this location.</p>'
    completed = {check["check_id"] for check in checks if check["status"] != "not_run"}
    if completed and completed <= {"V1", "V4"}:
        coverage += f'<p class="b-assurance-context">{escape(ui["validation_model_only"])}</p>'
    return f'<p class="b-v2-answer">{summary}</p>{coverage}'


def validation_table(checks: list[dict], *, totals: bool = False) -> None:
    """Show validation rows on the slides or with a summary on the dashboard."""
    ui = labels()
    if not checks:
        st.caption(ui["validation_empty"])
        return
    summary = _tally(checks, ui) if totals else ""
    st.markdown(
        f'{VALIDATION_STYLE}<div class="b-assurance b-validation">{summary}{_validation_markup(checks, ui)}</div>',
        unsafe_allow_html=True,
    )


def _datasets(bundle: dict, ui: dict) -> str:
    sources = dict.fromkeys(source for row in bundle["evidence"] for source in row["datasets"])
    checks = {check["check_id"]: check for check in bundle["validation"] if check["status"] != "not_run"}
    data = []
    for source in sources:
        if "MapSPAM" in source:
            data.append(("MapSPAM 2010", "About 10 km", "Circa 2010", "Which crops are grown nearby"))
        else:
            entry = next((details for prefix, details in DATASET_SOURCES.items() if source.startswith(prefix)),
                         ("Unspecified", "Unspecified", "Used in this replay"))
            data.append((source, *entry))
    if "V1" in checks:
        data.append((checks["V1"]["dataset"], "One worked example", "Daily", "Reference water-use calculation check"))
    if "V2" in checks and not any(name.startswith("GGCMI") for name, *_ in data):
        data.append((f'{checks["V2"]["version"]} crop calendar', "0.5°", "Crop calendar",
                     "Check whether regional crop dates fit together"))
    headings = ("Dataset", "Resolution", "Time step", "Used for")
    rows = []
    for name, resolution, time_step, purpose in data:
        cells = [
            _cell(headings[1], _prose(resolution)),
            _cell(headings[2], _prose(time_step)),
            _cell(headings[3], escape(purpose)),
        ]
        rows.append(f'<tr role="row"><th scope="row" role="rowheader">{escape(name)}</th>{"".join(cells)}</tr>')
    return _table(headings, "".join(rows), "b-assurance-data", ui["datasets_heading"])


def _section(heading: str, content: str, css: str = "") -> str:
    return f'<section class="b-v2-section {css}"><h2>{escape(heading)}</h2>{content}</section>'


def _bullets(lines) -> str:
    return "<ul>" + "".join(f"<li>{_prose(line)}</li>" for line in lines) + "</ul>"


def how_sure(bundle: dict) -> None:
    """Render the validation summary, all results and the data behind the replay."""
    ui = labels()
    checks = bundle["validation"]
    assumptions = tuple(dict.fromkeys(line for option in bundle["evidence"] for line in option["assumptions_L"]))
    st.markdown(
        f'{VALIDATION_STYLE}<div class="b-assurance">'
        + (_tally(checks, ui) if checks else f'<p class="b-v2-answer">{escape(ui["validation_empty"])}</p>')
        + _section(ui["validation"], _validation_markup(checks, ui), "b-assurance-primary b-validation")
        + '<div class="b-assurance-split">'
        + _section(ui["assumptions"], _bullets(assumptions) if assumptions else f'<p>{escape(ui["no_assumptions"])}</p>')
        + _section("Limitations", _bullets(ui["limits"]))
        + "</div>"
        + _section(ui["datasets_heading"], _datasets(bundle, ui))
        + _section(ui["satellites_heading"], f'<p class="b-assurance-methods">{escape(ui["satellites_text"])}</p>')
        + "</div>",
        unsafe_allow_html=True,
    )
