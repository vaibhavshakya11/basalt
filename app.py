from collections.abc import Callable
from logging import getLogger

import requests
import streamlit as st
from streamlit.components.v1 import html as component_html

from basalt.climate.power import PowerError
from basalt.config import DEMO_COORDS
from basalt.contracts import Scenario
from basalt.routes import ROUTE_FIELDS, Route, parse_route
from basalt.soil.soilgrids import SoilGridsUnavailable
from basalt.ui.components import apply_navigation, favicon, footer, goto, header, labels, text_with_numbers
from basalt.ui.field import field_view
from basalt.ui.howsure import how_sure
from basalt.ui import landing as landing_page
from basalt.ui.options import options_view
from basalt.ui.slides import slides_view

LOGGER = getLogger(__name__)
FIELDS_KEPT = 4
WORKSPACE_STYLE = """
<style>
.stApp .st-key-field-workspace{padding-top:16px}
.stApp .st-key-field-workspace [role="tablist"]{gap:24px;counter-reset:workspace-step}
.stApp .st-key-field-workspace button[role="tab"]{min-height:44px;padding-inline:0;gap:6px;font-weight:500}
.stApp .st-key-field-workspace button[role="tab"]::before{
 counter-increment:workspace-step;content:counter(workspace-step) / "";
 font:400 var(--type-xs)/1.4 'IBM Plex Mono',monospace;color:var(--ash);
}
.stApp .st-key-field-workspace button[role="tab"][aria-selected="true"]{font-weight:650;color:var(--iron)}
.stApp .st-key-field-workspace button[role="tab"]:focus-visible{outline-offset:-2px}
.stApp .b-field-context{color:var(--ash);font-size:var(--type-xs);margin:0}
@media(max-width:767px){
 .stApp .st-key-field-workspace [role="tablist"]{gap:12px}
 .stApp .st-key-field-workspace button[role="tab"]{font-size:14px;gap:4px}
}
</style>
"""
HISTORY_HANDLER = """
<script>
const scopes = [window.parent];
try {
  if (window.top !== window.parent && window.top.location.origin === window.parent.location.origin) {
    scopes.push(window.top);
  }
} catch (error) {
  if (error.name !== "SecurityError") throw error;
}
for (const host of scopes) {
  const routeListener = Symbol.for("basalt.history");
  if (host[routeListener]) continue;
  host[routeListener] = true;
  const route = () => host.location.pathname + host.location.search;
  let previousRoute = route();
  for (const method of ["pushState", "replaceState"]) {
    const original = host.history[method];
    host.history[method] = function (...args) {
      const result = original.apply(this, args);
      previousRoute = route();
      return result;
    };
  }
  host.addEventListener("popstate", () => {
    if (route() !== previousRoute) host.location.reload();
  });
  host.document.addEventListener("click", event => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (event.target.closest?.("[data-options-step]")) {
      const tabs = host.document.querySelectorAll('.st-key-field-workspace [role="tablist"] [role="tab"]');
      const options = tabs[1];
      if (!options) return;
      event.preventDefault();
      options.click();
      options.focus();
      options.scrollIntoView({block: "start", inline: "nearest"});
    } else if (event.target.closest?.("[data-field-edit]")) {
      const editor = host.document.querySelector('.st-key-field-editor details');
      const summary = editor?.querySelector('summary');
      if (!summary) return;
      event.preventDefault();
      if (!editor.open) summary.click();
      summary.focus();
      summary.scrollIntoView({block: "nearest", inline: "nearest"});
    }
  });
}
</script>
"""


def _load_demo(site_id: str) -> dict:
    from basalt.service import load_demo

    return load_demo(site_id)


@st.cache_data(show_spinner=False, max_entries=24)
def _refresh_demo(site_id: str, scenario: Scenario, **setup) -> dict:
    from basalt.service import demo_scenario

    return demo_scenario(site_id, scenario, **setup)


@st.cache_data(show_spinner=False, max_entries=24)
def _analyze(lat: float, lon: float, scenario: Scenario, **setup) -> dict:
    from basalt.service import analyze_location

    return analyze_location(lat, lon, scenario=scenario, **setup)


def _field_state(key: str) -> dict:
    st.session_state["active_field"] = key
    history = st.session_state.setdefault("field_history", {})
    field = history.pop(key, {"settings": {}})
    history[key] = field
    if len(history) > FIELDS_KEPT:
        del history[next(iter(history))]
    return field


def _stage_scenario(key: str, scenario: Scenario) -> None:
    if st.session_state.get("active_field") == key:
        st.session_state["field_history"][key]["pending"] = {"scenario": scenario}


def _actions() -> None:
    ui = labels()
    retry, back = st.columns([1, 1], gap="small")
    if retry.button(ui["try_again"], key="retry-field", type="primary"):
        st.rerun()
    if back.button(ui["open_demos"], key="field-demos"):
        goto()


def _choose_soil(field: dict) -> None:
    from basalt.knowledge.loader import load_soils

    ui = labels()
    st.title(ui["field_location"])
    st.warning(ui["choose_soil_hint"])
    with st.form("soil-fallback", border=False):
        soil = st.selectbox(ui["soil_type"], list(load_soils()), index=None,
                            format_func=lambda value: value.replace("_", " ").capitalize())
        if st.form_submit_button(ui["field_soil_apply"], type="primary"):
            if soil is None:
                st.error(ui["field_soil_error"])
            else:
                field["settings"] = {**field["settings"], "soil_class": soil}
                st.rerun()
    if st.button(ui["open_demos"], key="soil-demos"):
        goto()


def _render_tabs(bundle: dict, key: str, field: dict) -> None:
    ui = labels()
    story = bundle["field_story"]
    current = next(option for option in bundle["evidence"] if option["is_current"])
    st.markdown(WORKSPACE_STYLE, unsafe_allow_html=True)
    with st.container(key="field-workspace"):
        st.title(story["site"]["name"])
        start, end = current["season_range"]
        source = ui["field_pin_label"] if story["site"]["site_id"] == "custom" else ui["field_demo_label"]
        context = ui["field_context"].format(details=source, start=start, end=end)
        st.markdown(f'<p class="b-field-context">{text_with_numbers(context)}</p>', unsafe_allow_html=True)
        field_tab, options_tab, confidence_tab = st.tabs([ui["tab_field"], ui["tab_options"], ui["tab_sure"]])
        notice = field.get("notice")
        with field_tab:
            if notice and notice[0] == "field":
                st.warning(notice[1])
            elif field.pop("updated", False):
                st.success(ui["field_confirmed"])
            updated = field_view(bundle, key=key, editor_open=bool(notice and notice[0] == "field"))
        with options_tab:
            if notice and notice[0] == "scenario":
                st.warning(notice[1])
            options_view(bundle, key=key, on_scenario=lambda scenario: _stage_scenario(key, scenario))
        with confidence_tab:
            how_sure(bundle)
        if updated is not None:
            soil, irrigated, crops, constraints = updated
            field["pending"] = {"soil_class": soil, "irrigated": irrigated, "crop_ids": crops, "constraints": constraints}
            st.rerun()


def _resolve_field(field: dict, load: Callable[..., dict]) -> dict:
    from basalt.service import replay_snapshot

    pending = field.get("pending")
    if "bundle" in field and pending is not None:
        complete = all(field["settings"].get(name, Scenario() if name == "scenario" else None) == value
                       for name, value in pending.items())
        if complete:
            field.pop("pending")
            field.pop("notice", None)
            return field["bundle"]

    settings = {**field["settings"], **(pending or {})}
    scenario = settings.get("scenario", Scenario())
    if "bundle" in field and pending and set(pending) == {"scenario"}:
        bundle = replay_snapshot(field["bundle"], scenario)
    else:
        setup = {name: value for name, value in settings.items() if name != "scenario"}
        bundle = load(scenario, **setup)
    field.update(settings=settings, bundle=bundle)
    if pending and "scenario" not in pending:
        field["updated"] = True
    field.pop("pending", None)
    field.pop("notice", None)
    return bundle


def _show_field(route: Route, load: Callable[..., dict]) -> None:
    from basalt.service import FieldInputError

    ui = labels()
    field = _field_state(route.key)
    # Preserve the tabs' frontend position when the initial spinner is removed.
    progress = st.container()
    try:
        if "bundle" in field:
            bundle = _resolve_field(field, load) if "pending" in field else field["bundle"]
        else:
            label = "lookup_field" if route.kind == "pin" else "replaying"
            with progress, st.spinner(ui[label]):
                bundle = _resolve_field(field, load)
    except SoilGridsUnavailable:
        _choose_soil(field)
        return
    except (FileNotFoundError, ValueError, RuntimeError, requests.RequestException) as error:
        if isinstance(error, FieldInputError):
            message = str(error)
        elif isinstance(error, PowerError):
            message = ui["weather_unavailable"]
        elif isinstance(error, FileNotFoundError) and route.kind == "demo":
            message = ui["demo_unavailable"]
        else:
            LOGGER.warning("Field replay failed: %s", type(error).__name__)
            message = ui["field_update_unavailable"] if "bundle" in field else ui["field_data_unavailable"]
        pending = field.pop("pending", {})
        if "bundle" not in field:
            st.error(message)
            _actions()
            return
        kind = "scenario" if set(pending) == {"scenario"} else "field"
        field["notice"] = (kind, f'{message} {ui["valid_results_kept"]}')
        bundle = field["bundle"]

    _render_tabs(bundle, route.key, field)


def _landing(error: str | None = None) -> None:
    if error:
        st.warning(labels()[error])
    try:
        preview = _load_demo("ludhiana")
    except FileNotFoundError:
        preview = None
    landing_page.landing(preview)


def run() -> None:
    """Route offline demos, public field pins and presentation slides."""
    st.set_page_config(page_title="basalt", page_icon=favicon(), layout="wide", initial_sidebar_state="collapsed")
    apply_navigation()
    with st.container(key="browser-history"):
        st.markdown("<style>.st-key-browser-history{display:none}</style>", unsafe_allow_html=True)
        component_html(HISTORY_HANDLER, width=0, height=0, tab_index=-1)
    query = st.query_params
    parameters = {name: query.get_all(name) for name in ROUTE_FIELDS if name in query}
    if parameters == {"view": ["demo-fields"]}:
        header()
        landing_page.directory_page()
        footer()
        return
    route = parse_route(parameters)
    site_name = None
    if route.site is not None:
        site_name = DEMO_COORDS[route.site][0]
    elif route.coordinates is not None:
        lat, lon = route.coordinates
        site_name = f"{lat:.4f}, {lon:.4f}"
    header(site_name)
    st.session_state["active_field"] = route.key
    if route.kind == "slides":
        try:
            slides_view(_load_demo("ludhiana"), _load_demo("malawi"))
        except FileNotFoundError:
            st.error(labels()["demo_unavailable"])
            if st.button(labels()["open_demos"]):
                goto()
    elif route.site is not None:
        def demo(scenario, **setup):
            if scenario == Scenario() and not setup:
                return _load_demo(route.site)
            return _refresh_demo(route.site, scenario, **setup)

        _show_field(route, demo)
    elif route.coordinates is not None:
        _show_field(route, lambda scenario, **setup: _analyze(*route.coordinates, scenario, **setup))
    else:
        _landing(route.error)
    footer()


if __name__ == "__main__":
    run()
