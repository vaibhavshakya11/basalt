from streamlit.testing.v1 import AppTest


HARNESS = """
import streamlit as st
from basalt.ui.field import field_inputs

bundle = {
    "setup": {
        "soil_class": "loam",
        "soil_classes": ["sand", "loam"],
        "crop_options": {"maize": "Maize"},
        "crop_options_by_water": {
            "rainfed": {"maize": "Maize"},
            "irrigated": {"rice": "Rice"},
        },
        "current_crop_ids": ["maize"],
        "irrigated": False,
    },
    "field_story": {"tier": "global"},
}
change = field_inputs(bundle, key="test-field")
if change:
    st.write(change)
"""


def test_editing_water_source_filters_crops_and_reports_empty_selection():
    screen = AppTest.from_string(HARNESS).run()
    assert not screen.exception
    assert screen.multiselect[0].options == ["Maize"]
    screen.radio(key="field-water-test-field").set_value("irrigated").run()
    assert not screen.exception
    assert screen.multiselect[0].options == ["Rice"]
    assert screen.multiselect[0].value == []
    assert screen.number_input[0].value is None
    screen.button[0].click().run()
    assert "Choose at least one current crop" in screen.error[0].value


def test_water_source_without_supported_crops_shows_an_explanation():
    setup = HARNESS.replace('"irrigated": {"rice": "Rice"}', '"irrigated": {}')
    screen = AppTest.from_string(setup).run()
    screen.radio(key="field-water-test-field").set_value("irrigated").run()
    assert not screen.exception
    assert "No supported crop calendar" in screen.info[0].value
    assert not screen.button
