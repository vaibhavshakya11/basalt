import json
import re

from basalt.contracts import Evidence
from basalt.decision.replay import copy_templates
from basalt.physics.soilhealth import FACTORS

IRRIGATION_FLAG = re.compile(r"needs_more_irrigation_than_available_in_(\d+)_of_(\d+)")


def render_stability(evidence: Evidence) -> str:
    """Explain the evidence's sensitivity badge using its named drivers."""
    copy = copy_templates()["stability"]
    stability = evidence["stability"]
    if stability["badge"] == "robust":
        return copy["robust"]
    return copy["depends"].format(drivers=", ".join(driver["label"] for driver in stability["drivers"]))


def _explain(records: list[str], templates: dict[str, str]) -> list[str]:
    explain = []
    for record in records:
        entry = json.loads(record)
        if entry["rule"] in templates:
            explain.append(templates[entry["rule"]].format(**entry))
    return explain


def _evidence(evidence: Evidence, current: Evidence, irrigated: bool, calendar_source: str, copy: dict) -> list[str]:
    values = evidence["metrics"]
    baseline = current["metrics"]
    texts = copy["evidence"]
    start, stop = evidence["season_range"]
    soil = values["soil_score"]
    lines = [
        texts["overview"].format(n=evidence["n_seasons"], start=start, end=stop),
        texts["comparison"].format(
            soil=soil["median"], soil_p10=soil["p10"], soil_p90=soil["p90"], current_soil=baseline["soil_score"]["median"],
            et=values["et_mm"]["median"], current_et=baseline["et_mm"]["median"],
        ),
    ]
    if irrigated:
        lines.append(texts["pumping"].format(irr=values["irr_gross_mm"]["median"], current_irr=baseline["irr_gross_mm"]["median"]))
    lines.append(texts["calendar"].format(calendar_source=copy["calendar_sources"][calendar_source]))
    return lines


def _benefits(evidence: Evidence, current: Evidence, copy: dict) -> list[str]:
    lines = [copy["tags"][tag]["description"] for tag in evidence["tags"]]
    options = evidence["metrics"]["soil_factors"]
    baseline = current["metrics"]["soil_factors"]
    for factor in FACTORS:
        option = options[factor]["median"]
        comparison = baseline[factor]["median"]
        if option + 1e-12 >= comparison + 0.10:
            lines.append(copy["benefits"]["soil_factor"].format(
                factor_name=copy["soil_factors"][factor].lower(), current=comparison, option=option,
            ))
    return lines or [copy["benefits"]["comparable"]]


def _gaps(evidence: Evidence, calendar_source: str, copy: dict) -> list[str]:
    keys = copy["gaps"]
    lines = [keys["disease"], *evidence["gaps"]]
    lines.extend(copy["stability_drivers"][driver["param"]]["local"] for driver in evidence["stability"]["drivers"])
    if evidence["tier"] == "global":
        lines.append(keys["regional_ndvi" if calendar_source == "ndvi" else "global"])
    return [*lines, keys["income"]]


def constraint_warnings(evidence: Evidence) -> list[str]:
    """Translate the machine-readable flags used to advise local review."""
    copy = copy_templates()["risks"]
    warnings = []
    for flag in evidence["constraints_flags"]:
        if flag == "assured_market_dropped":
            warnings.append(copy[flag])
        elif match := IRRIGATION_FLAG.fullmatch(flag):
            warnings.append(copy["irrigation"].format(k=match[1], n=match[2]))
    return warnings


def build_card(evidence: Evidence, current: Evidence, *, irrigated: bool, calendar_source: str) -> dict[str, list[str]]:
    """Render the five fixed evidence sections for a rotation card."""
    copy = copy_templates()
    reasons = _explain(evidence["why"], copy["why"])
    if not reasons:
        key = "current" if evidence["is_current"] else evidence["rotation_id"]
        reasons = [copy["why"][key]] if key in copy["why"] else []
    risks_copy = copy["risks"]
    risks = [*constraint_warnings(evidence), *_explain(evidence["risks"], risks_copy)]
    if evidence["lever"] == "fill_the_gap" or "cover" in evidence["tags"]:
        risks.append(risks_copy["gap_crop"])
    return {
        "why": reasons,
        "evidence": _evidence(evidence, current, irrigated, calendar_source, copy),
        "benefits": _benefits(evidence, current, copy),
        "gaps": _gaps(evidence, calendar_source, copy),
        "risks": [*risks, risks_copy["local"]],
    }
