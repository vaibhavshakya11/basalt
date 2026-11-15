import argparse
import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

from basalt.config import ROOT

CHART = '[data-testid="stPlotlyChart"] .main-svg'
DEFAULT_TIMEOUT = 45000


def _port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def _app_server():
    port = _port()
    base = f"http://127.0.0.1:{port}"
    command = [sys.executable, "-m", "streamlit", "run", "app.py", "--server.address=127.0.0.1",
               f"--server.port={port}", "--server.headless=true", "--server.fileWatcherType=none"]
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
    page.locator(selector).filter(visible=True).first.wait_for(state="visible")
    page.evaluate("document.fonts.ready")
    alerts = page.locator('[data-testid="stException"]')
    if alerts.count():
        raise RuntimeError(alerts.first.inner_text())


def _save(page: Page, destination: Path, filename: str, *, full_page: bool = True) -> None:
    page.screenshot(path=destination / filename, full_page=full_page, animations="disabled")


def _tab(page: Page, label: str) -> None:
    page.get_by_role("tab", name=label, exact=True).click()


def _set_scenario(page: Page) -> None:
    page.get_by_text("Try a different climate", exact=True).click()
    sliders = page.get_by_role("slider")
    temperature = sliders.nth(sliders.count() - 2)
    rain = sliders.nth(sliders.count() - 1)
    temperature.focus()
    temperature.press("Home")
    for _ in range(4):
        temperature.press("ArrowRight")
    rain.focus()
    rain.press("Home")
    for _ in range(4):
        rain.press("ArrowRight")
    page.get_by_role("button", name="Replay this climate", exact=True).click()
    page.get_by_text("Scenario: +2 °C, -10% rain", exact=True).wait_for(state="visible")


def _capture_desktop(page: Page, base: str, destination: Path) -> dict[str, float]:
    page.goto(base, wait_until="domcontentloaded")
    _ready(page)
    _save(page, destination, "01_landing.png")

    start = time.monotonic()
    page.get_by_role("button", name="Try Ludhiana, India", exact=True).click()
    page.wait_for_url("**/?site=ludhiana")
    _ready(page)
    timings = {"ludhiana_demo_seconds": time.monotonic() - start}
    _save(page, destination, "02_ludhiana_field.png")
    _tab(page, "Your options")
    _ready(page)
    _save(page, destination, "03_ludhiana_options.png")
    page.get_by_text("Details", exact=True).nth(1).click()
    page.get_by_text("Why suggested", exact=True).filter(visible=True).nth(0).wait_for(state="visible")
    _save(page, destination, "04_ludhiana_card_details.png")
    _tab(page, "How sure are we?")
    _ready(page, ".b-validation")
    _save(page, destination, "05_ludhiana_how_sure.png")
    _tab(page, "Your options")
    page.get_by_text("Details", exact=True).nth(1).click()
    _set_scenario(page)
    _ready(page)
    _save(page, destination, "08_slider_scenario.png")

    page.goto(base, wait_until="domcontentloaded")
    _ready(page)
    start = time.monotonic()
    page.get_by_role("button", name="Try central Malawi", exact=True).click()
    page.wait_for_url("**/?site=malawi")
    _ready(page)
    timings["malawi_demo_seconds"] = time.monotonic() - start
    _save(page, destination, "06_malawi_field.png")
    _tab(page, "Your options")
    page.get_by_text("Why not more options?", exact=True).wait_for(state="visible")
    _save(page, destination, "07_malawi_options.png")
    return timings


def _capture_mobile(page: Page, base: str, destination: Path) -> dict:
    page.goto(base, wait_until="domcontentloaded")
    _ready(page)
    layout = page.evaluate("""() => {
        const view = document.querySelector('[data-testid="stAppViewBlockContainer"]');
        const chart = document.querySelector('[data-testid="stPlotlyChart"]');
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
    return layout


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
    parser = argparse.ArgumentParser(description="Capture Basalt's real demo screens with headless Chromium.")
    parser.add_argument("--base-url")
    parser.add_argument("--destination", type=Path, default=ROOT / "review" / "screenshots")
    parser.add_argument("--chromium-executable")
    args = parser.parse_args()
    if args.base_url:
        audit = capture(args.base_url, args.destination, args.chromium_executable)
    else:
        with _app_server() as base:
            audit = capture(base, args.destination, args.chromium_executable)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
