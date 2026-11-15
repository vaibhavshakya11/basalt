import json

from basalt.config import DEMO
from basalt.ui.options import _option_head, _year_results
from basalt.ui.strata import farming_year_label, strata_figure


def _demo_chart():
    archive = json.loads((DEMO / "ludhiana" / "bundle.json").read_text())
    return archive, archive["strata"][archive["field_story"]["current_rotation_id"]]


def test_farming_year_labels_follow_actual_calendar_boundary():
    assert farming_year_label(2024, "06-01") == "2024/25"
    assert farming_year_label(2024, "01-01") == "2024"


def test_strata_orders_archive_and_can_show_only_crop_cover():
    _, archive = _demo_chart()
    rows = list(reversed(archive["rows"]))
    figure = strata_figure({**archive, "rows": rows}, events=())
    assert len(figure.data) == 1
    assert list(figure.data[0].y) == sorted(row["season"] for row in rows)
    assert figure.layout.yaxis.title.text == "Farming year"
    assert figure.layout.xaxis.title.text == "Months of the farming year"
    assert figure.layout.yaxis.ticktext[-1] == "2024/25"
    assert any("The soil was bare." in day for row in figure.data[0].customdata for day in row)


def test_option_counts_come_from_paired_evidence(monkeypatch):
    bundle, _ = _demo_chart()
    option = next(row for row in bundle["evidence"] if row["rotation_id"] == "pb_mw")
    html = []
    monkeypatch.setattr("basalt.ui.options.st.markdown", lambda markup, **unused: html.append(markup))
    _option_head(option, irrigated=True)
    _year_results(option)
    assert 'class="b-axis-counts"' not in html[0]
    for tally in option["wins_vs_current"].values():
        better, worse, tie = tally["better"], tally["worse"], tally["tie"]
        assert f'{better}</span> better · <span class="b-count">{worse}</span> worse · <span class="b-count">{tie}</span>' in html[1]
