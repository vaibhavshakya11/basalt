import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from basalt.config import DATA, DEMO_COORDS

COLUMNS = ["latitude", "longitude", "acq_date", "confidence", "type"]
YEARS = tuple(range(2012, 2025))
EARTH_RADIUS_KM = 6371.0088
ARCHIVE = "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp"


def _download_year(target: Path, year: int) -> Path:
    filename = f"viirs-snpp_{year}_India.csv"
    destination = target / filename
    if destination.is_file():
        return destination
    partial = destination.with_suffix(".csv.part")
    with requests.get(f"{ARCHIVE}/{year}/{filename}", timeout=(20, 120), stream=True) as response:
        response.raise_for_status()
        with partial.open("wb") as stream:
            for block in response.iter_content(chunk_size=1024 * 1024):
                stream.write(block)
    with partial.open() as stream:
        if not set(COLUMNS).issubset(stream.readline().strip().split(",")):
            raise ValueError(f"NASA did not return the expected FIRMS CSV for {year}")
    partial.replace(destination)
    return destination


def _distance_km(lat: pd.Series, lon: pd.Series) -> np.ndarray:
    _, site_lat, site_lon = DEMO_COORDS["ludhiana"]
    lat_delta = np.radians(lat - site_lat)
    lon_delta = np.radians(lon - site_lon)
    half_chord = np.sin(lat_delta / 2) ** 2 + np.cos(np.radians(site_lat)) * np.cos(
        np.radians(lat)
    ) * np.sin(lon_delta / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(half_chord, 0, 1)))


def archive_pentads(paths: list[Path]) -> pd.DataFrame:
    available_years = set()
    fire_days = []
    for path in paths:
        for observations in pd.read_csv(path, usecols=COLUMNS, chunksize=100_000,
                                        parse_dates=["acq_date"]):
            days = observations["acq_date"]
            available_years.update(days.dt.year.dropna().unique())
            thermal = observations["type"].eq(0) & observations["confidence"].str.lower().isin(["n", "h"])
            autumn = observations.loc[thermal & days.dt.month.ge(9)]
            local = _distance_km(autumn["latitude"], autumn["longitude"]) <= 25
            fire_days.append(autumn.loc[local, "acq_date"])
    missing_years = set(YEARS) - available_years
    if missing_years:
        raise ValueError(f"Missing FIRMS archive years: {', '.join(map(str, sorted(missing_years)))}")
    counts = pd.concat(fire_days).value_counts()
    pentads = []
    for year in YEARS:
        start = pd.Timestamp(year, 9, 1)
        end = pd.Timestamp(year, 12, 31)
        for pentad, first in enumerate(pd.date_range(start, end, freq="5D"), start=1):
            dates = pd.date_range(first, min(first + pd.Timedelta(days=4), end))
            daily = [int(counts.get(day, 0)) for day in dates]
            pentads.append((year, pentad, first, dates[-1], sum(daily), daily))
    return pd.DataFrame(pentads, columns=("year", "pentad", "start", "end", "fires", "daily_counts"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate India S-NPP science-quality FIRMS CSVs")
    parser.add_argument("archives", nargs="*", type=Path)
    parser.add_argument("--download-dir", type=Path, help="Download the public India archives to this directory")
    parser.add_argument("--output", type=Path, default=DATA / "firms" / "ludhiana_pentads.parquet")
    options = parser.parse_args()
    if options.download_dir:
        options.download_dir.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths = list(pool.map(lambda year: _download_year(options.download_dir, year), YEARS))
    elif options.archives:
        paths = options.archives
    else:
        parser.error("Supply the annual CSV files or set --download-dir")
    pentads = archive_pentads(paths)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    pentads.to_parquet(options.output, index=False, compression="zstd")
    print(f"Retained {pentads.fires.sum():,} detections over {len(YEARS)} years")


if __name__ == "__main__":
    main()
