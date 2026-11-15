import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import local
from time import sleep

import numpy as np
import pandas as pd
import requests

from basalt.config import CACHE

ORNL_URL = "https://modis.ornl.gov/rst/api/v1"
NDVI_PRODUCT = "MOD13Q1"
ET_PRODUCT = "MOD16A2GF"
ET_FALLBACK = "MOD16A2"
NDVI_BAND = "250m_16_days_NDVI"
NDVI_QC = "250m_16_days_pixel_reliability"
ET_BAND = "ET_500m"
ET_QC = "ET_QC_500m"
START = "2001-01-01"
END = "2024-12-31"
CHUNK_SIZE = 8
TIMEOUT_SECONDS = 20
_thread = local()


class ORNLError(ValueError):
    """ORNL reported missing or unreadable MODIS subsets."""


def _write_atomic(path: Path, write) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=path.suffix, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        write(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _request(path: str, params: dict, cache: Path, timeout: int) -> dict:
    if cache.is_file():
        return json.loads(cache.read_text())
    if not hasattr(_thread, "client"):
        _thread.client = requests.Session()
    for attempt in range(3):
        try:
            response = _thread.client.get(
                f"{ORNL_URL}/{path}", params=params, headers={"Accept": "application/json"}, timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()
            _write_atomic(cache, lambda target: target.write_bytes(response.content))
            return content
        except requests.RequestException as error:
            if attempt == 2:
                raise ORNLError(f"MODIS subset {path} could not be downloaded.") from error
            sleep(2 ** attempt)


def _middle_pixels(values: list[int], height: int, width: int) -> np.ndarray:
    grid = np.asarray(values, dtype=np.int32).reshape(height, width)
    row, col = height // 2, width // 2
    return grid[max(0, row - 1):row + 2, max(0, col - 1):col + 2].ravel()


def _usable_pixels(values: np.ndarray, quality: np.ndarray, product: str) -> np.ndarray:
    if product == NDVI_PRODUCT:
        return (values >= -2000) & (values <= 10000) & np.isin(quality, (0, 1))
    # Accept usable backup-algorithm ET values as well as main-algorithm retrievals.
    return (values >= -32767) & (values <= 32700) & (quality >= 0) & (quality <= 254) & ((quality >> 5) <= 3)


def _read_subset(response: dict, product: str) -> dict:
    if product == NDVI_PRODUCT:
        value_band, quality_band, scale = NDVI_BAND, NDVI_QC, 0.0001
    else:
        value_band, quality_band, scale = ET_BAND, ET_QC, 0.1
    height, width = (int(response[key]) for key in ("nrows", "ncols"))
    both_bands = {}
    for band in response["subset"]:
        if band["band"] in (value_band, quality_band):
            both_bands.setdefault(band["calendar_date"], {})[band["band"]] = _middle_pixels(band["data"], height, width)
    summaries = {}
    for day, bands in both_bands.items():
        if value_band not in bands or quality_band not in bands:
            continue
        values = bands[value_band]
        valid = values[_usable_pixels(values, bands[quality_band], product)]
        summaries[day] = (float(np.median(valid) * scale) if valid.size else np.nan, int(valid.size))
    return summaries


def _fetch_series(
    product: str, lat: float, lon: float, start: str, end: str, value_name: str, cache_dir: Path,
    workers: int, timeout: int, chunk_size: int,
) -> pd.DataFrame:
    if not 1 <= chunk_size <= 10:
        raise ValueError("ORNL accepts a maximum of ten composites per request.")
    coordinates = {"latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}"}
    key = f"{product}_{coordinates['latitude']}_{coordinates['longitude']}"
    cache = cache_dir / f"{key}_{start}_{end}.parquet"
    if cache.is_file():
        return pd.read_parquet(cache)
    staging = cache_dir / "ornl_raw" / key
    returned_dates = _request(f"{product}/dates", coordinates, staging / "dates.json", timeout)["dates"]
    dates = sorted(
        (row for row in returned_dates if start <= row["calendar_date"] <= end),
        key=lambda row: row["calendar_date"],
    )
    if not dates:
        raise ORNLError(f"No {product} dates are available for this location and period.")

    def fetch(chunk: list[dict]) -> dict:
        first, last = (chunk[index]["modis_date"] for index in (0, -1))
        params = {**coordinates, "startDate": first, "endDate": last, "kmAboveBelow": 1, "kmLeftRight": 1}
        response = _request(f"{product}/subset", params, staging / f"{first}_{last}.json", timeout)
        return _read_subset(response, product)

    chunks = [dates[offset:offset + chunk_size] for offset in range(0, len(dates), chunk_size)]
    summaries = {}
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        requests_by_chunk = [(chunk, executor.submit(fetch, chunk)) for chunk in chunks]
        for chunk, subset_request in requests_by_chunk:
            try:
                summaries.update(subset_request.result())
            except ORNLError as error:
                if timeout <= TIMEOUT_SECONDS:
                    for _, pending in requests_by_chunk:
                        pending.cancel()
                    raise
                failures.append((chunk[0]["modis_date"], chunk[-1]["modis_date"], error))
    if failures:
        first, last, error = failures[0]
        raise ORNLError(f"{len(failures)} {product} batches failed. First failed range: {first}–{last}.") from error
    calendar_dates = [day["calendar_date"] for day in dates]
    observations = pd.DataFrame(
        [summaries.get(day, (np.nan, 0)) for day in calendar_dates],
        index=pd.DatetimeIndex(calendar_dates, name="date"), columns=[value_name, "valid_pixels"],
    )
    observations.attrs.update(
        product=product, version="061", source="ORNL DAAC MODIS Subset Web Service",
        latitude=float(coordinates["latitude"]), longitude=float(coordinates["longitude"]),
        pixels="3 × 3 centered on the selected point",
        fetched_utc=datetime.now(timezone.utc).isoformat(),
        rejected_composite_share=float((observations["valid_pixels"] == 0).mean()),
    )
    _write_atomic(cache, observations.to_parquet)
    return observations


def fetch_ndvi(
    lat: float, lon: float, *, start: str = START, end: str = END,
    cache_dir: Path = CACHE, workers: int = 3, timeout: int = TIMEOUT_SECONDS, chunk_size: int = CHUNK_SIZE,
) -> pd.DataFrame:
    """Get center-pixel NDVI medians and accepted pixel counts for each composite."""
    return _fetch_series(NDVI_PRODUCT, lat, lon, start, end, "ndvi", cache_dir, workers, timeout, chunk_size)


def fetch_modis_et(
    lat: float, lon: float, *, start: str = START, end: str = END,
    cache_dir: Path = CACHE, workers: int = 3, timeout: int = TIMEOUT_SECONDS, chunk_size: int = CHUNK_SIZE,
) -> pd.DataFrame:
    """Get the MOD16 composite water depth and accepted pixel count."""
    catalog = _request("products", {}, cache_dir / "ornl_raw" / "products.json", timeout)
    products = {entry["product"] for entry in catalog["products"]}
    product = ET_PRODUCT if ET_PRODUCT in products else ET_FALLBACK
    if product not in products:
        raise ORNLError("The ORNL catalog has no MOD16 evapotranspiration product.")
    return _fetch_series(product, lat, lon, start, end, "et_mm", cache_dir, workers, timeout, chunk_size)
