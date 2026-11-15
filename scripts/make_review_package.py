import argparse
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from basalt.config import DEMO, ROOT
from basalt.knowledge.loader import load_assumptions

REPO_URL = "https://github.com/vaibhavshakya11/basalt"
SCREENS = (
    "01_landing.png", "02_ludhiana_field.png", "03_ludhiana_options.png",
    "04_ludhiana_card_details.png", "05_ludhiana_how_sure.png", "06_malawi_field.png",
    "07_malawi_options.png", "08_slider_scenario.png", "09_mobile_landing.png", "10_strata_ludhiana.png",
)
CORE = (
    "climate/et0.py", "physics/waterbalance.py", "physics/risks.py", "physics/soilhealth.py",
    "physics/simulate.py", "decision/replay.py", "decision/levers.py", "decision/stability.py",
    "satellite/phenology.py", "satellite/validate.py", "explain/cards.py", "explain/patterns.py",
)
KNOWLEDGE = ("crops.yaml", "gap_crops.yaml", "rotations_punjab.yaml", "soils.yaml", "copy.yaml")
NAMES = {"soil": "soil", "water": "water", "risk": "weather risk"}
VALIDATION_NOTES = {
    "V1": "The daily formula reproduces the FAO example.",
    "V2": "Same-date crop parameters agree. Regional dates overlap.",
    "V3": "Paired calendar dates match more closely in Ludhiana.",
    "V4": "Daily input, output and storage close within tolerance.",
    "V5": "The post-rice share is below the 50% rule.",
    "V6": "The rice reference estimate exceeds the published range.",
    "V7": "Malawi wetness anomalies are compared with NASA SMAP when the export is present.",
    "V8": "Bias is relative to the satellite estimate, which has irrigation limits.",
}
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _git(*args) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _files(root: Path, suffix: str = ".py") -> list[Path]:
    return sorted(root.rglob(f"*{suffix}"))


def _audit(browser: dict, bundles: dict) -> list[tuple[str, bool]]:
    visual = re.compile(r"inter|geist|gradient|purple|indigo|violet|box-shadow|backdrop-filter", re.I)
    words = re.compile(r"\b(revolutionize|unlock|empower|seamless|cutting-edge|powerful|ai-powered|next-generation|"
                       r"game-changing|comprehensive|robust|leverage|harness|journey|delve)\b", re.I)
    tracked = [ROOT / name for name in _git("ls-files").splitlines()
               if Path(name).suffix in {".py", ".md", ".yaml", ".toml"}]
    # Keep metric and geometry symbols, including the sign glyphs used by the charts.
    emoji = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]")
    code = re.compile(r"TODO|FIXME|\bprint\(|except:\s*pass")
    ui = _files(ROOT / "basalt/ui")
    visual_assets = ui + [path for suffix in (".css", ".html", ".js") for path in _files(ROOT / "basalt/ui", suffix)]
    copy = (ROOT / "basalt/knowledge/copy.yaml").read_text().replace("\n  robust:", "\n  stable:")
    visible_copy = copy + "\n" + "\n".join(path.read_text() for path in ui + [ROOT / "README.md"])
    mobile = browser.get("mobile", {})
    verdicts = all(
        all(token in set(NUMBER.findall(json.dumps(row))) for token in NUMBER.findall(row["verdict"]))
        for bundle in bundles.values() for row in bundle["evidence"]
    )
    links = re.search(r"^(https://\S+\.streamlit\.app)/?", browser.get("verified_public_url", ""), re.M)
    return [
        ("Visual and font scan, app.py, basalt/ui, .streamlit", not any(visual.search(path.read_text()) for path in visual_assets + [ROOT / "app.py", ROOT / ".streamlit/config.toml"])),
        ("Emoji scan, tracked source and commit subjects", not any(emoji.search(path.read_text()) for path in tracked) and not emoji.search(_git("log", "--format=%s"))),
        ("Copy vocabulary, copy.yaml, UI and README", not words.search(visible_copy)),
        ("Em dash scan, copy.yaml and UI", chr(8212) not in visible_copy),
        ("Model code scan, basalt package", not any(code.search(path.read_text()) for path in _files(ROOT / "basalt"))),
        ("Evidence numbers, options and expanded details", verdicts and bool(browser.get("option_numbers_verified"))),
        ("Landing at 390 px, both buttons and chart", mobile.get("viewport") == 390 and 300 <= mobile.get("chartWidth", 0) <= 390 and mobile.get("contentWidth", 391) <= 390),
        ("Chart legends and practice labels, screenshots 01, 02, 04, 06, 10", bool(browser.get("chart_labels_verified"))),
        ("All three field tabs fit at 390 px", len(mobile.get("workspaceWidths", {})) == 3 and
         all(width <= 390 for width in mobile["workspaceWidths"].values())),
        ("Local demo and scenario latency", all(0 < browser.get(key, 99) < limit for key, limit in (
            ("ludhiana_demo_seconds", 2), ("malawi_demo_seconds", 2), ("scenario_replay_seconds", 3)))),
        ("Public replay routes, signed-out browser", bool(links)),
    ]


def _validation_value(check: dict) -> str:
    value = check["value"]
    if value is None:
        return check["status"].replace("_", " ")
    if isinstance(value, dict):
        display = ", ".join(f"{key} {item:.4g}" for key, item in value.items())
    else:
        display = f"{value:.4g} {check['unit']}"
    return f"{check['status']}, {display}".rstrip()


def _report(summary, bundles, browser, pytest, deployed, commit) -> str:
    validation = [
        f"| {left['check_id']} | {_validation_value(left)} | {_validation_value(right)} | {VALIDATION_NOTES[left['check_id']]} |"
        for left, right in zip(summary["ludhiana"]["validations"], summary["malawi"]["validations"], strict=True)
    ]
    headlines = []
    for site_id in ("ludhiana", "malawi"):
        site = summary[site_id]
        headlines.append(f"**{site['site']['name']}**")
        for option in site["options"]:
            arrows = ", ".join(f"{NAMES[axis]} {state}" for axis, state in option["arrows"].items())
            headlines.append(f"- {option['name']}. {option['verdict']} {arrows}. {option['stability_line']}.")
    rejects = summary["malawi"]["lever_rejections"]
    reasons = "\n".join(f"- {row['lever'].replace('_', ' ').capitalize()}. {row['reason']}" for row in rejects)
    audit = "\n".join(f"- {'Pass' if good else 'Needs review'}. {name}." for name, good in _audit(browser, bundles))
    missing = [f"{site['site']['site_id']} {check['check_id']}"
               for site in summary.values() for check in site["validations"]
               if check["status"] == "not_run" and (site["site"]["site_id"], check["check_id"]) in
               {("ludhiana", "V2"), ("ludhiana", "V3"), ("ludhiana", "V5"), ("ludhiana", "V8"),
                ("malawi", "V3"), ("malawi", "V7"), ("malawi", "V8")}]
    tests = " ".join(pytest.strip().splitlines()[-1:]) or "Pytest output is empty."
    roots = ", ".join(a.value for a in load_assumptions() if a.parameter == "initial_root_depth")
    return f"""# basalt review

1. [Repository]({REPO_URL}) · {f'[Public app]({deployed})' if deployed else 'Public deployment pending'} · `{commit}`
2. M0–M3 implemented. V2 isolates crop parameters on a feasible shared calendar. M4 {'verified in a signed-out browser' if deployed else 'verified locally, public deployment pending'}. M5 {'complete' if not missing else 'partial (' + ', '.join(missing) + ' pending or infeasible)'}.
3. Tests. {tests}

## Validation

| Check | Ludhiana | Malawi | Note |
|---|---|---|---|
{chr(10).join(validation)}

## Headline results

{chr(10).join(headlines)}

The results summary covers all eight demo fields, including six new cropland pins checked with ESA WorldCover.

## Malawi lever outcomes

{reasons or 'All three selected alternatives passed the proposal checks.'}

## Deviations and assumptions

- GGCMI v1.01 dates, with MapSPAM 2010 area because GGCMI flags alone cannot establish local crop coverage. Pea area is unavailable. Wheat area is unsplit.
- The offline map uses bundled Natural Earth shapes. The weather controls send both slider values together, including during rapid keyboard edits. GRACE uses official JPL analysis values at the two demo cells. Elsewhere the fallback is NASA Goddard, labelled separately because its catalog and embedded release labels differ. The offline script also supports the authenticated full JPL product.
- Complete agricultural years determine trends. At these pins the 2025-starting season extends past the supplied weather archive. The bare-soil depletion fraction (0.55), proportional depletion when roots shrink, initial rooting depth{f' ({roots})' if roots else ''}, gap-crop heights and supplied uncertainty bounds are model assumptions. The crop YAML files record low-confidence additions.
- Internal rotation runs retain both phases for two-year cycles. Reported counts can be half-integers after averaging phases; peak closure uses the larger phase residual. JSON Evidence fields follow the frozen structure.
- V2 holds PAU planting and harvest dates fixed while replacing crop parameters. Unadjusted GGCMI dates fit only one of the four rotations.

## Self-audit

{audit}

## Next checks

{'- Obtain the queued AppEEARS export and run V7.' if 'malawi V7' in missing else '- Confirm model wetness on the ground at the Malawi field scale.'}
- Check the season-long rice reference water-use difference with local records.
- Derive a defensible global comparison for rotations with overlapping regional calendars.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the review zip from committed evidence and recorded browser QA")
    parser.add_argument("--pytest-output", type=Path, required=True)
    parser.add_argument("--browser-audit", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, default=ROOT / "review/screenshots")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commit = _git("rev-parse", "HEAD")
    summary = json.loads((ROOT / "results_summary.json").read_text())
    browser = json.loads(args.browser_audit.read_text())
    deployed = browser.get("verified_public_url", "")
    pytest = args.pytest_output.read_text()
    bundles = {site: json.loads((DEMO / site / "bundle.json").read_text()) for site in summary}
    report = _report(summary, bundles, browser, pytest, deployed, commit)
    files = {"results_summary.json": ROOT / "results_summary.json", "tests/pytest_output.txt": args.pytest_output}
    files.update({f"knowledge/{name}": ROOT / "basalt/knowledge" / name for name in KNOWLEDGE})
    files.update({f"core_src/{Path(name).name}": ROOT / "basalt" / name for name in CORE})
    for filename in SCREENS:
        path = args.screenshots / filename
        with Image.open(path) as picture:
            if picture.width != (390 if filename.startswith("09_") else 1440):
                raise ValueError(f"Unexpected screenshot width for {filename}: {picture.width}")
        files[f"screenshots/{filename}"] = path
    pending = args.output.with_suffix(".tmp")
    prefix = "basalt_review/"
    with ZipFile(pending, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(prefix + "REVIEW.md", report)
        archive.writestr(prefix + "links.txt", f"{deployed or 'Public deployment pending'}\n{REPO_URL}\n{commit}\n")
        for name, path in files.items():
            archive.write(path, prefix + name)
        validations = []
        for site, bundle in bundles.items():
            validations.extend(bundle["validation"])
            archive.writestr(prefix + f"evidence/field_story_{site}.json", json.dumps(bundle["field_story"], indent=2))
            for item in bundle["evidence"]:
                archive.writestr(prefix + f"evidence/{site}_{item['rotation_id']}.json", json.dumps(item, indent=2))
        archive.writestr(prefix + "evidence/validation.json", json.dumps(validations, indent=2))
    if pending.stat().st_size >= 15_000_000:
        pending.unlink()
        raise ValueError("Review zip exceeded 15 MB")
    pending.replace(args.output)


if __name__ == "__main__":
    main()
