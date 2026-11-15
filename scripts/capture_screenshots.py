import argparse
import json
import re
import socket
import subprocess
import sys
import time
from math import ceil
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

from basalt.config import DEMO, ROOT
from basalt.knowledge.loader import read_yaml

CHART = '.js-plotly-plot .main-svg:has(.ytick)'
FIELD_CHART = f'[role="tabpanel"]:visible {CHART}'
SCENARIO = 'iframe[title$="basalt_climate_scenario"]'
DEFAULT_TIMEOUT = 45000
NUMBER = r"-?\d+(?:\.\d+)?"


def _port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def _app_server():
    port = _port()
    base = f"http://127.0.0.1:{port}"
    command = [sys.executable, "-m", "streamlit", "run", "app.py", "--server.address=127.0.0.1",
               f"--server.port={port}", "--server.headless=true", "--server.fileWatcherType=none",
               "--global.developmentMode=false"]
    with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL) as process:
        try:
            for _ in range(60):
                try:
                    with urlopen(f"{base}/_stcore/health", timeout=1) as reply:
                        if reply.status == 200:
                            break
                except (URLError, TimeoutError):
                    if process.poll() is not None:
                        raise RuntimeError("Streamlit stopped before it could serve the demos.")
                    time.sleep(.25)
            else:
                raise RuntimeError("Streamlit did not start.")
            yield base
        finally:
            process.terminate()


def _ready(page: Page, selector: str = CHART) -> None:
    alerts = page.locator('[data-testid="stException"]:visible')
    ready = page.locator(selector).filter(visible=True)
    ready.or_(alerts).first.wait_for(state="visible")
    if alerts.count():
        raise RuntimeError(alerts.first.inner_text())
    page.evaluate("document.fonts.ready")
    page.locator("[data-stale=true]:visible").first.wait_for(state="hidden")


def _save(page: Page, destination: Path, filename: str) -> None:
    page.evaluate("""async () => {
        const active = document.getAnimations().filter(animation =>
            animation.playState === 'running' && Number.isFinite(animation.effect?.getComputedTiming().endTime));
        await Promise.race([
            Promise.all(active.map(animation => animation.finished.catch(() => null))),
            new Promise(resolve => setTimeout(resolve, 800)),
        ]);
    }""")
    viewport = page.viewport_size
    content = page.locator('[data-testid="stMainBlockContainer"], [data-testid="stAppViewBlockContainer"], .block-container').first
    full_height = ceil(content.evaluate("(el) => Math.max(0, el.getBoundingClientRect().top) + el.scrollHeight")) + 8
    page.set_viewport_size({"width": viewport["width"], "height": max(viewport["height"], full_height)})
    page.evaluate("""() => {
        window.scrollTo(0, 0);
        for (const node of document.querySelectorAll('[data-testid="stAppViewContainer"], [data-testid="stMain"]')) {
            node.scrollTo(0, 0);
        }
    }""")
    page.screenshot(path=destination / filename, full_page=True, animations="disabled")
    page.set_viewport_size(viewport)


def _tab(page: Page, label: str) -> None:
    page.get_by_role("tab", name=label, exact=True).click()


def _wait_for_field(page: Page, site: str, bundle: dict) -> None:
    page.wait_for_function("site => new URL(location.href).searchParams.get('site') === site", arg=site)
    page.get_by_role("heading", name=bundle["field_story"]["site"]["name"], exact=True).wait_for()
    _ready(page, FIELD_CHART)
    page.get_by_role("heading", name="Where the calendar came from", exact=True).wait_for()


def _set_scenario(page: Page) -> float:
    ui = read_yaml("copy.yaml")["ui"]
    page.get_by_text(ui["scenario"], exact=True).click()
    controls = page.frame_locator(SCENARIO)
    presets = ((ui["warm"], 2., .5), (ui["rain"], -10., 5.))
    for label, target, step in presets:
        handle = controls.get_by_role("slider", name=label, exact=True)
        current = float(handle.input_value())
        count = round((target - current) / step)
        for _ in range(abs(count)):
            handle.press("ArrowRight" if count > 0 else "ArrowLeft")
        if float(handle.input_value()) != target:
            raise RuntimeError(f"Could not set the climate slider {label!r}")
    banner = page.get_by_text(ui["scenario_banner"].format(temperature=2, rain=-10), exact=True)
    if page.locator(".b-scenario:visible").count():
        raise RuntimeError("The draft changed the replay before it was applied")
    start = time.monotonic()
    controls.get_by_role("button", name=ui["scenario_apply"], exact=True).click()
    banner.wait_for(state="visible")
    _ready(page, FIELD_CHART)
    return time.monotonic() - start


def _bundle(site: str) -> dict:
    return json.loads((DEMO / site / "bundle.json").read_text(encoding="utf-8"))


def _audit_chart_labels(page: Page, views: list[dict]) -> bool:
    ui = read_yaml("copy.yaml")["ui"]
    families = {segment[3] for strata in views for row in strata["rows"] for segment in row["segments"]}
    expected = {ui["categories"][family] for family in families}
    expected.update(ui["events"].values())
    legend = page.locator(".b-chart-legend").filter(visible=True).inner_text()
    return all(word in legend for word in expected)


def _audit_option_numbers(page: Page, bundle: dict, *, expanded: bool = False) -> bool:
    options = bundle["evidence"]
    actual = {item.get_attribute("data-rotation"): item.inner_text() for item in page.locator(".b-verdict:visible").all()}
    expected = {option["rotation_id"]: option["verdict"] for option in options}
    if actual != expected:
        return False

    layout = read_yaml("copy.yaml")["ui"]["option_count_line"]
    counts = {option["rotation_id"]: [layout.format(**option["wins_vs_current"][axis])
              for axis in ("soil", "water", "risk")] for option in options if not option["is_current"]}
    measured = {
        card.locator(".b-verdict").get_attribute("data-rotation"): card.locator(".b-axis-counts").all_inner_texts()
        for card in page.locator('.b-option-head[data-current="false"]:visible').all()
    }
    if measured != counts:
        return False

    year_axes = [axis.text_content() or "" for axis in page.locator(".yaxislayer-above:visible").all()]
    years = {season for option in options for season in range(option["season_range"][0], option["season_range"][1] + 1)}
    if any(int(year) not in years for axis in year_axes for year in re.findall(r"\b(20\d{2})/", axis)):
        return False
    if not expanded:
        return True

    baseline = next(option for option in options if option["is_current"])
    visible_text = page.locator('[role="tabpanel"]:visible').inner_text()
    for option in options:
        if option["is_current"]:
            continue
        card = bundle["cards"][option["rotation_id"]]
        sections = [line for section in card.values() for line in section]
        if not sections or any(line not in visible_text for line in sections):
            continue
        evidence_numbers = [float(value) for value in re.findall(NUMBER, json.dumps([option, baseline]))]
        practice_numbers = [icon.inner_text() for icon in page.locator(".b-practice .b-count:visible").all()]
        visible_numbers = map(float, re.findall(NUMBER, " ".join(sections + practice_numbers)))
        return all(any(abs(number - reported) <= max(.5, abs(reported) * .01) for reported in evidence_numbers)
                   for number in visible_numbers)
    return False


def _capture_desktop(page: Page, base: str, destination: Path) -> dict:
    ludhiana, malawi = _bundle("ludhiana"), _bundle("malawi")
    page.goto(base, wait_until="domcontentloaded")
    _ready(page)
    chart_audited = _audit_chart_labels(page, [ludhiana["strata"][ludhiana["field_story"]["current_rotation_id"]]])
    _save(page, destination, "01_landing.png")

    start = time.monotonic()
    page.get_by_role("button", name="Try Ludhiana, India", exact=True).click()
    _wait_for_field(page, "ludhiana", ludhiana)
    timings = {"ludhiana_demo_seconds": time.monotonic() - start}
    _save(page, destination, "02_ludhiana_field.png")
    _tab(page, "Your options")
    _ready(page, FIELD_CHART)
    option_audited = _audit_option_numbers(page, ludhiana)
    chart_audited &= _audit_chart_labels(page, list(ludhiana["strata"].values()))
    _save(page, destination, "03_ludhiana_options.png")
    page.get_by_text("Details", exact=True).nth(1).click()
    page.get_by_text("Why suggested", exact=True).filter(visible=True).nth(0).wait_for(state="visible")
    option_audited &= _audit_option_numbers(page, ludhiana, expanded=True)
    option_audited &= page.locator(".b-practice .b-practice-row:visible").count() >= 12
    page.wait_for_function("""() => {
        const last = [...document.querySelectorAll('details[open] .b-practice-row')].at(-1);
        return last && last.getBoundingClientRect().bottom <= last.closest('details').getBoundingClientRect().bottom + 1;
    }""")
    _save(page, destination, "04_ludhiana_card_details.png")
    _tab(page, "How sure are we?")
    _ready(page, ".b-validation .b-check")
    _save(page, destination, "05_ludhiana_how_sure.png")
    _tab(page, "Your options")
    page.get_by_text("Details", exact=True).nth(1).click()
    timings["scenario_replay_seconds"] = _set_scenario(page)
    _save(page, destination, "08_slider_scenario.png")
    ui = read_yaml("copy.yaml")["ui"]
    page.frame_locator(SCENARIO).get_by_role("button", name=ui["scenario_reset"], exact=True).click()
    page.locator(".b-scenario").wait_for(state="detached")
    page.get_by_role("tab", name=ui["tab_options"], exact=True, selected=True).wait_for(state="visible")

    page.goto(base, wait_until="domcontentloaded")
    _ready(page)
    start = time.monotonic()
    page.get_by_role("button", name="Try central Malawi", exact=True).click()
    _wait_for_field(page, "malawi", malawi)
    timings["malawi_demo_seconds"] = time.monotonic() - start
    chart_audited &= _audit_chart_labels(page, [malawi["strata"][malawi["field_story"]["current_rotation_id"]]])
    _save(page, destination, "06_malawi_field.png")
    _tab(page, "Your options")
    page.get_by_text("Why not more options?", exact=True).wait_for(state="visible")
    _ready(page, FIELD_CHART)
    option_audited &= _audit_option_numbers(page, malawi)
    chart_audited &= _audit_chart_labels(page, list(malawi["strata"].values()))
    _save(page, destination, "07_malawi_options.png")
    return {**timings, "option_numbers_verified": option_audited, "chart_labels_verified": chart_audited}


def _capture_mobile(page: Page, base: str, destination: Path) -> dict:
    page.goto(base, wait_until="domcontentloaded")
    _ready(page)
    layout = page.evaluate("""() => {
        const view = document.querySelector('[data-testid="stMainBlockContainer"], [data-testid="stAppViewBlockContainer"], .block-container');
        const chart = document.querySelector('.js-plotly-plot');
        return {viewport: window.innerWidth, contentWidth: view.scrollWidth, chartWidth: chart.clientWidth}
    }""")
    if layout["viewport"] != 390 or layout["contentWidth"] > 390 or layout["chartWidth"] < 300:
        raise ValueError(f"Mobile landing layout exceeded the available width: {layout}")
    _save(page, destination, "09_mobile_landing.png")
    for label in ("Try Ludhiana, India", "Try central Malawi"):
        button = page.get_by_role("button", name=label, exact=True)
        button.scroll_into_view_if_needed()
        if not button.is_enabled():
            raise RuntimeError(f"Cannot reach the '{label}' demo at 390 px")
    ui = read_yaml("copy.yaml")["ui"]
    page.get_by_role("button", name=ui["demo_malawi"], exact=True).tap()
    _wait_for_field(page, "malawi", _bundle("malawi"))
    page.get_by_text(ui["field_edit"], exact=True).tap()
    page.get_by_text(ui["field_water_mode"], exact=True).last.wait_for(state="visible")
    workspace_widths = {}
    for item in ("tab_field", "tab_options", "tab_sure"):
        page.get_by_role("tab", name=ui[item], exact=True).tap()
        _ready(page, ".b-validation .b-check" if item == "tab_sure" else FIELD_CHART)
        page.wait_for_function("""() => {
            const workspace = document.querySelector('[data-testid="stMainBlockContainer"], .block-container');
            return workspace.scrollWidth <= window.innerWidth;
        }""")
        workspace_widths[item] = page.locator(".block-container").evaluate("(node) => node.scrollWidth")
    return {**layout, "workspaceWidths": workspace_widths}


def capture(base: str, destination: Path, executable: str | None = None) -> dict:
    """Capture real demo views in a clean browser and check phone layout."""
    destination.mkdir(parents=True, exist_ok=True)
    origin = urlsplit(base).netloc
    blocked = []
    with sync_playwright() as playwright:
        with playwright.chromium.launch(headless=True, executable_path=executable) as browser:
            desktop = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True,
                                     has_touch=True)
            for page in (desktop, phone):
                page.set_default_timeout(DEFAULT_TIMEOUT)

                def local_only(route):
                    url = route.request.url
                    if urlsplit(url).netloc in {"", origin}:
                        route.continue_()
                    else:
                        blocked.append(url)
                        route.abort()

                page.route("**/*", local_only)
            timings = _capture_desktop(desktop, base, destination)
            layout = _capture_mobile(phone, base, destination)
    return {**timings, "mobile": layout, "external_requests": blocked}


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture basalt's real demo screens with headless Chromium.")
    parser.add_argument("--base-url")
    parser.add_argument("--destination", type=Path, default=ROOT / "review" / "screenshots")
    parser.add_argument("--chromium-executable")
    parser.add_argument("--audit-json", type=Path, default=ROOT / "review" / "browser_audit.json")
    args = parser.parse_args()
    if args.base_url:
        audit = capture(args.base_url, args.destination, args.chromium_executable)
    else:
        with _app_server() as base:
            audit = capture(base, args.destination, args.chromium_executable)
    payload = json.dumps(audit, indent=2) + "\n"
    args.audit_json.parent.mkdir(parents=True, exist_ok=True)
    args.audit_json.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
