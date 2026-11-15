from zipfile import ZipFile

import pandas as pd
import pytest

from scripts.fetch_smap_appeears import LAYER, _bundle_samples, _payload, daily_wetness


def _point_rows() -> pd.DataFrame:
    coordinates = _payload()["params"]["coordinates"]
    rows = [
        (point["latitude"], point["longitude"], "2020-02-29T01:30:00Z", 0.4)
        for point in coordinates
    ]
    first = rows[0]
    rows.extend([
        (*first[:2], "2020-02-29T04:30:00Z", 0.8),
        (*first[:2], "2020-02-29T07:30:00Z", -9999),
        (*first[:2], "2025-01-01T01:30:00Z", 0.9),
    ])
    return pd.DataFrame(rows, columns=["Latitude", "Longitude", "Date", f"SPL4SMGP_008_{LAYER}"])


def test_appeears_bundle_reads_the_expected_version_and_point_results(tmp_path):
    source = _point_rows()
    path = tmp_path / "malawi.zip"
    with ZipFile(path, "w") as bundle:
        bundle.writestr("basalt-malawi/basalt-malawi-SPL4SMGP-008-results.csv", source.to_csv(index=False))
        bundle.writestr("basalt-malawi-SPL4SMGP-007-results.csv", "wrong-version\n")
        bundle.writestr("basalt-malawi-SPL4SMGP-008-statistics.csv", "statistics-only\n")
    (loaded,) = _bundle_samples(path)
    pd.testing.assert_frame_equal(loaded, source)


def test_valid_samples_are_averaged_in_time_then_space():
    daily = daily_wetness([_point_rows()])
    assert daily.date.tolist() == [pd.Timestamp("2020-02-29")]
    assert daily.sm_rootzone_wetness.iloc[0] == pytest.approx((0.6 + 8 * 0.4) / 9)


def test_other_locations_or_versions_cannot_fill_the_malawi_validation_input():
    samples = _point_rows()
    wrong_version = samples.rename(columns={f"SPL4SMGP_008_{LAYER}": f"SPL4SMGP_007_{LAYER}"})
    with pytest.raises(ValueError, match="V8 root-zone wetness"):
        daily_wetness([wrong_version])
    first = samples.iloc[0]
    other_points = samples[~(samples.Latitude.eq(first.Latitude) & samples.Longitude.eq(first.Longitude))]
    with pytest.raises(ValueError, match="nine requested Malawi points"):
        daily_wetness([other_points])
