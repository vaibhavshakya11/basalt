import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr

from basalt.config import DEMO_COORDS
from basalt.global_tier.grace import GLOBAL_TABLE, GSFC_DATASET, JPL_DATASET, TABLE
from basalt.global_tier.ggcmi import ggcmi_cell

PRODUCT = "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4"
JPL_SOURCE = f"https://podaac.jpl.nasa.gov/dataset/{PRODUCT}"
GSFC_SOURCE = "https://earth.gsfc.nasa.gov/geo/data/grace-mascons"
GSFC_FILENAME = "GSFC.glb_.200204_202606_RL06v2.0_OBP-ICE6GD_HALFDEGREE.nc"
GSFC_DOWNLOAD = f"https://earth.gsfc.nasa.gov/sites/default/files/geo/{GSFC_FILENAME}"
JPL_DEMO_SOURCE = "https://grace.jpl.nasa.gov/data-analysis-tool/"
JPL_TIME_SERIES = "https://grace-onearth.jpl.nasa.gov/nexus/timeSeriesSpark"


def get_mascon(download_dir: Path) -> Path:
    import earthaccess

    if not all(os.environ.get(name) for name in ("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD")):
        raise ValueError("Set EARTHDATA_USERNAME and EARTHDATA_PASSWORD in the local environment")
    earthaccess.login(strategy="environment", persist=False)
    matches = earthaccess.search_data(short_name=PRODUCT)
    if not matches:
        raise RuntimeError(f"No NASA granules found for {PRODUCT}")
    download_dir.mkdir(parents=True, exist_ok=True)
    paths = earthaccess.download(matches, local_path=str(download_dir))
    if len(paths) != 1:
        raise RuntimeError(f"Expected one active JPL monthly time-series file, received {len(paths)}")
    return Path(paths[0])


def get_gsfc_mascon(download_dir: Path) -> Path:
    download_dir.mkdir(parents=True, exist_ok=True)
    destination = download_dir / GSFC_FILENAME
    if destination.is_file():
        return destination
    partial = destination.with_suffix(".nc.part")
    with requests.get(GSFC_DOWNLOAD, stream=True, timeout=(20, 180)) as response:
        response.raise_for_status()
        with partial.open("wb") as stream:
            for block in response.iter_content(chunk_size=1024 * 1024):
                stream.write(block)
    partial.replace(destination)
    return destination


def _deseasonalized_slopes(values: np.ndarray, dates: pd.DatetimeIndex) -> np.ndarray:
    """Regress monthly anomalies against elapsed decimal years using available months."""
    elapsed = ((dates - dates[0]).days.to_numpy(dtype=float) / 365.2425)[:, None]
    flat = values.reshape(len(dates), -1).astype("float64")
    for month in range(1, 13):
        row = dates.month == month
        month_rows = flat[row]
        count = np.isfinite(month_rows).sum(axis=0)
        means = np.divide(np.nansum(month_rows, axis=0), count, out=np.zeros(len(count)), where=count > 0)
        flat[row] = month_rows - means
    available = np.isfinite(flat)
    count = available.sum(axis=0)
    sum_x = np.sum(np.where(available, elapsed, 0), axis=0)
    sum_x2 = np.sum(np.where(available, elapsed ** 2, 0), axis=0)
    sum_y = np.nansum(flat, axis=0)
    sum_xy = np.nansum(flat * elapsed, axis=0)
    denominator = count * sum_x2 - sum_x ** 2
    slope = np.divide(count * sum_xy - sum_x * sum_y, denominator, out=np.full(flat.shape[1], np.nan),
                      where=(count >= 2) & (denominator > 0))
    return slope.reshape(values.shape[1:])


def _write_trends(output: Path, trend: np.ndarray, lat: np.ndarray, lon: np.ndarray,
                  start: pd.Timestamp, end: pd.Timestamp, label: str, source: str,
                  detail: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, lat=lat, lon=lon, trend_cm_per_yr=trend,
                        period_start=start.strftime("%Y-%m"), period_end=end.strftime("%Y-%m"),
                        dataset=label, source_url=source, source_detail=detail)


def build_grid(input_file: Path, output: Path, product: str = "jpl") -> None:
    with xr.open_dataset(input_file) as dataset:
        water = dataset["lwe_thickness"].transpose("time", "lat", "lon")
        if water.attrs.get("units") not in {"cm", "centimeters", "centimetres"}:
            raise ValueError(f"Expected equivalent water height in cm, got {water.attrs.get('units')}")
        dates = pd.DatetimeIndex(water.time.values)
        selected = (dates >= "2002-04-01") & ~((dates >= "2017-07-01") & (dates < "2018-06-01"))
        dates = dates[selected]
        trend = np.full((water.sizes["lat"], water.sizes["lon"]), np.nan, dtype=np.float32)
        for start in range(0, water.sizes["lat"], 12):
            band = slice(start, start + 12)
            trend[band] = _deseasonalized_slopes(water.isel(time=selected, lat=band).values, dates)

        land = dataset["land_mask"].transpose("lat", "lon").values == 1
        trend[~land] = np.nan
        if "scale_factor" in dataset:
            gain = dataset["scale_factor"].transpose("lat", "lon").values
            use_gain = land & np.isfinite(gain)
            trend[use_gain] *= gain[use_gain]
            print(f"Applied NASA land gain factors for {use_gain.sum():,} grid cells")
        else:
            print("No land gain factors supplied in the NetCDF")
        label, source = (GSFC_DATASET, GSFC_SOURCE) if product == "gsfc" else (JPL_DATASET, JPL_SOURCE)
        if product == "gsfc":
            header = dataset.attrs.get("product_version", "unspecified")
            detail = f"Public NASA Goddard grid. The catalog labels it RL06v2.0. The file header lists {header}."
        else:
            detail = "NASA JPL monthly land mascon grid."
        _write_trends(output, trend, water.lat.values, water.lon.values, dates[0], dates[-1],
                      label, source, detail)
    print(f"{label}: wrote {len(dates)} monthly time steps to {output}")


def _demo_months(lat: float, lon: float, path: Path) -> pd.Series:
    start = pd.Timestamp("2002-04-01", tz="UTC")
    stop = pd.Timestamp.now(tz="UTC")
    query = {
        "ds": f"{PRODUCT}_LAND", "minLat": lat - .249, "maxLat": lat + .249,
        "minLon": lon - .249, "maxLon": lon + .249, "startTime": int(start.timestamp()),
        "endTime": int(stop.timestamp()), "mask": 3, "lowPassFilter": "False",
        "seasonalFilter": "false",
    }
    if path.is_file():
        document = json.loads(path.read_bytes())
    else:
        response = requests.get(JPL_TIME_SERIES, params=query, timeout=90)
        response.raise_for_status()
        document = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    metadata = document["meta"][0]
    bounds = metadata["bounds"]
    for key, expected in (("north", query["maxLat"]), ("south", query["minLat"]),
                          ("east", query["maxLon"]), ("west", query["minLon"])):
        if not np.isclose(bounds[key], expected, rtol=0, atol=0.0001):
            raise ValueError(f"Unexpected GRACE cell bounds in {path}")
    records = [row for month in document["data"] for row in month if row.get("cnt") == 1]
    dates = pd.to_datetime([row["time"] for row in records], unit="s")
    values = pd.Series([row["mean"] for row in records], index=dates, dtype=float).dropna().sort_index()
    if (metadata["shortName"] != query["ds"] or len(values) < 2
            or values.index[0].to_period("M") != start.tz_localize(None).to_period("M")
            or values.index.has_duplicates):
        raise ValueError(f"Unrecognised or incomplete NASA JPL analysis series in {path}")
    return values.loc[~((values.index >= "2017-07-01") & (values.index < "2018-06-01"))]


def build_demo_grid(directory: Path, output: Path) -> None:
    cells = {site_id: ggcmi_cell(lat, lon) for site_id, (_, lat, lon) in DEMO_COORDS.items()}
    latitudes = sorted({lat for lat, _ in cells.values()})
    longitudes = sorted({lon for _, lon in cells.values()})
    trend = np.full((len(latitudes), len(longitudes)), np.nan, dtype="float32")
    starts, ends = [], []
    for site_id, (lat, lon) in cells.items():
        months = _demo_months(lat, lon, directory / f"grace-jpl-{site_id}.json")
        slope = float(_deseasonalized_slopes(months.to_numpy()[:, None], months.index)[0])
        trend[latitudes.index(lat), longitudes.index(lon)] = slope
        starts.append(months.index[0])
        ends.append(months.index[-1])
        print(f"{site_id}: {len(months)} NASA JPL samples, {slope:.3f} cm per year")
    _write_trends(output, trend, np.asarray(latitudes), np.asarray(longitudes), max(starts), min(ends),
                  JPL_DATASET, JPL_DEMO_SOURCE,
                  "Public NASA JPL Analysis Tool subsets for the demo cells. Separate gain factors were unavailable.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build land-water storage trends from NASA GRACE and GRACE-FO")
    parser.add_argument("--input", type=Path, help="Local equivalent-water-height NetCDF")
    parser.add_argument("--product", choices=("jpl", "jpl-demo", "gsfc"), default="jpl")
    parser.add_argument("--download-dir", type=Path, default=Path("data/cache/grace"))
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    if options.product == "jpl-demo":
        build_demo_grid(options.download_dir, options.output or TABLE)
        return
    reader = get_gsfc_mascon if options.product == "gsfc" else get_mascon
    input_file = options.input or reader(options.download_dir)
    out = options.output or (GLOBAL_TABLE if options.product == "gsfc" else TABLE)
    build_grid(input_file, out, options.product)


if __name__ == "__main__":
    main()
