from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep

import numpy as np
import pandas as pd
import requests

from basalt.climate.et0 import reference_et0, saturation_vapor_pressure
from basalt.config import CACHE
from basalt.contracts import CLIMATE_UNITS, ClimateTable

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_FIELDS = {
    "T2M_MAX": ("tmax", "C"),
    "T2M_MIN": ("tmin", "C"),
    "T2MDEW": ("tdew", "C"),
    "RH2M": ("rh", "%"),
    "WS2M": ("ws2", "m/s"),
    "ALLSKY_SFC_SW_DWN": ("rs", "MJ/m^2/day"),
    "PRECTOTCORR": ("precip", "mm/day"),
    "PS": ("ps", "kPa"),
}
POWER_SOURCE = "NASA POWER daily, AG community"
BASELINE_START = "1990-01-01"
BASELINE_END = "2025-12-31"


class PowerError(ValueError):
    """The POWER response is unavailable or unsuitable for replay."""


def _interpolate_short_gaps(series: pd.Series) -> pd.Series:
    missing = series.isna()
    gap_lengths = missing.groupby(missing.ne(missing.shift()).cumsum()).transform("sum")
    filled = series.interpolate(method="linear", limit_area="inside")
    return series.mask(missing & (gap_lengths <= 3), filled)


def _fill_humidity(table: ClimateTable) -> None:
    # FAO-56 Eqs. 11 and 19 are inverse expressions for the same vapour pressure.
    es = (saturation_vapor_pressure(table["tmax"]) + saturation_vapor_pressure(table["tmin"])) / 2
    dew_gaps = table["tdew"].isna() & table["rh"].gt(0)
    if dew_gaps.any():
        vapor = table.loc[dew_gaps, "rh"] * es[dew_gaps] / 100
        log_pressure = np.log(vapor / 0.6108)
        table.loc[dew_gaps, "tdew"] = 237.3 * log_pressure / (17.27 - log_pressure)
    rh_gaps = table["rh"].isna() & table["tdew"].notna()
    if rh_gaps.any():
        table.loc[rh_gaps, "rh"] = 100 * saturation_vapor_pressure(table.loc[rh_gaps, "tdew"]) / es[rh_gaps]


def _assert_climate(table: ClimateTable) -> None:
    if list(table.columns) != list(CLIMATE_UNITS) or table.attrs.get("units") != CLIMATE_UNITS:
        raise PowerError("Climate cache schema or units do not match the replay contract.")
    if (
        not isinstance(table.index, pd.DatetimeIndex)
        or table.index.name != "date"
        or table.empty
        or not table.index.equals(pd.date_range(table.index[0], table.index[-1], name="date"))
    ):
        raise PowerError("Climate records must have one row per consecutive day.")
    if not np.isfinite(table[["tmax", "tmin", "tdew", "rh", "ws2", "precip", "ps", "et0"]]).all().all():
        raise PowerError("Daily weather has missing or non-finite values required by the model.")
    if table["qc_filled"].dtype != bool:
        raise PowerError("Climate quality markers must be Boolean.")


def parse_power(payload: dict, *, fetched_utc: str | None = None) -> ClimateTable:
    """Validate one NASA POWER API response and compute its climate table."""
    header = payload["header"]
    units = payload["parameters"]
    for code, (_, expected_unit) in POWER_FIELDS.items():
        received = units[code]["units"]
        if received != expected_unit:
            raise PowerError(f"NASA POWER reports {received} for {code}. Expected {expected_unit}.")
    lon, lat, elevation = payload["geometry"]["coordinates"]
    observations = payload["properties"]["parameter"]
    series = {name: observations[code] for code, (name, _) in POWER_FIELDS.items()}
    table = pd.DataFrame(series, dtype=float).replace(float(header["fill_value"]), np.nan)
    table.index = pd.to_datetime(table.index, format="%Y%m%d")
    start, end = (pd.to_datetime(header[key], format="%Y%m%d") for key in ("start", "end"))
    table = table.reindex(pd.date_range(start, end, name="date"))
    missing = table.isna().any(axis=1)
    table = table.apply(_interpolate_short_gaps)
    _fill_humidity(table)
    table.attrs.update(
        lat=lat, lon=lon, elevation_m=elevation, source=POWER_SOURCE,
        fetched_utc=fetched_utc or datetime.now(timezone.utc).isoformat(),
        scenario_dT=0.0, scenario_rain_mult=1.0, units=CLIMATE_UNITS.copy(),
        api_version=header["api"]["version"], time_standard=header["time_standard"],
        source_products=header["sources"],
    )
    table["et0"] = reference_et0(table)
    table["qc_filled"] = missing
    _assert_climate(table)
    return table


def write_climate(table: ClimateTable, path: Path) -> None:
    """Persist validated climate and metadata atomically as parquet."""
    _assert_climate(table)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as temp:
        temporary_path = Path(temp.name)
    try:
        table.to_parquet(temporary_path)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def load_climate(path: Path) -> ClimateTable:
    """Load an offline or cached climate table and check daily units."""
    table = pd.read_parquet(path)
    _assert_climate(table)
    return table


def fetch_power(
    lat: float, lon: float, start: str = BASELINE_START, end: str = BASELINE_END,
    *, cache_dir: Path = CACHE,
) -> ClimateTable:
    """Fetch NASA POWER Agroclimatology weather, or use its half-degree cache."""
    start_date, end_date = (pd.Timestamp(day).strftime("%Y%m%d") for day in (start, end))
    cache = cache_dir / f"power_{round(lat * 2) / 2:.1f}_{round(lon * 2) / 2:.1f}_{start_date}_{end_date}.parquet"
    if cache.is_file():
        return load_climate(cache)
    query = {
        "parameters": ",".join(POWER_FIELDS), "community": "AG",
        "longitude": lon, "latitude": lat, "start": start_date, "end": end_date, "format": "JSON",
    }
    for attempt in range(3):
        try:
            response = requests.get(POWER_URL, params=query, timeout=60)
            response.raise_for_status()
            payload = response.json()
            break
        except requests.RequestException as error:
            if attempt == 2:
                raise PowerError("NASA POWER weather is currently unavailable.") from error
            sleep(2 ** attempt)
    try:
        table = parse_power(payload)
    except (KeyError, TypeError) as error:
        raise PowerError("NASA POWER returned an unexpected response.") from error
    if table.index[0] != pd.Timestamp(start) or table.index[-1] != pd.Timestamp(end):
        raise PowerError("NASA POWER returned only part of the requested date range.")
    write_climate(table, cache)
    return table
