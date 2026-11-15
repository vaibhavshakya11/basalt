import argparse
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import requests
import xarray as xr

from basalt.config import DATA
from basalt.global_tier.ggcmi import COLUMNS

ZENODO = "https://zenodo.org/api/records/5062513"
DATAVERSE = "https://dataverse.harvard.edu"
GGCMI_FILENAME = re.compile(r"(?P<crop>[a-z0-9]+)_(?P<system>ir|rf)_ggcmi_crop_calendar_phase3_v1\.01\.nc4")
SPAM_CODES = {
    "bar": "BARL", "bea": "BEAN", "cas": "CASS", "cot": "COTT", "mai": "MAIZ",
    "mil": "PMIL", "nut": "GROU", "pot": "POTA", "rap": "RAPE",
    "ri1": "RICE", "ri2": "RICE", "rye": "OCER", "sor": "SORG", "soy": "SOYB",
    "sgb": "SUGB", "sgc": "SUGC", "sun": "SUNF", "swh": "WHEA", "wwh": "WHEA",
}
SPAM_NAME = "spam2010v2r0_global_harv_area.geotiff.zip"
SPAM_DOWNLOAD = f"https://s3.amazonaws.com/mapspam-data/2010/v2.0/geotiff/{SPAM_NAME}"
SPAM_METADATA = f"{DATAVERSE}/api/datasets/:persistentId/"
AREA_ROW = 2 * np.pi * 6371008.8 ** 2 / 720 / 10000 * np.diff(
    np.sin(np.deg2rad(np.linspace(-90, 90, 361)))
)


def download_verified(url: str, destination: Path, checksum: str) -> Path:
    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "md5").hexdigest()

    if destination.exists() and digest(destination) == checksum:
        return destination
    partial = destination.with_suffix(destination.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with partial.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                stream.write(chunk)
    if digest(partial) != checksum:
        raise ValueError(f"Checksum mismatch for {destination.name}")
    partial.replace(destination)
    return destination


def fetch_sources(inputs: Path) -> tuple[list[Path], Path]:
    inputs.mkdir(parents=True, exist_ok=True)
    response = requests.get(ZENODO, timeout=40)
    response.raise_for_status()
    records = [entry for entry in response.json()["files"] if GGCMI_FILENAME.fullmatch(entry["key"])]
    with ThreadPoolExecutor(max_workers=4) as pool:
        calendars = list(pool.map(lambda entry: download_verified(
            f"https://zenodo.org/records/5062513/files/{entry['key']}?download=1",
            inputs / entry["key"], entry["checksum"].removeprefix("md5:")), records))
    response = requests.get(SPAM_METADATA, params={"persistentId": "doi:10.7910/DVN/PRFF8V"}, timeout=40)
    response.raise_for_status()
    files = response.json()["data"]["latestVersion"]["files"]
    entry = next(entry["dataFile"] for entry in files if entry["label"] == SPAM_NAME)
    spam = download_verified(SPAM_DOWNLOAD, inputs / SPAM_NAME, entry["md5"])
    return calendars, spam


def _grid_indices(lat, lon):
    rows = np.floor((lat + 90) * 2).astype(int)
    cols = np.floor(((lon + 180) % 360) * 2).astype(int)
    return rows, cols


def _area_grid(dataset):
    band = dataset.read(1, masked=True).filled(0.0)
    ty = dataset.transform
    lat = ty.f + ty.e * (np.arange(band.shape[0]) + 0.5)
    lon = ty.c + ty.a * (np.arange(band.shape[1]) + 0.5)
    rows, cols = _grid_indices(lat, lon)
    index = 720 * rows[:, None] + cols[None, :]
    return np.bincount(index.ravel(), weights=np.maximum(0, band).ravel(), minlength=360 * 720).reshape(360, 720)


def harvested_areas(archive: Path, supported: set[str]) -> dict[tuple[str, str], np.ndarray]:
    import rasterio

    arrays = {}
    with ZipFile(archive) as zip_stream:
        filenames = zip_stream.namelist()
        has_rainfed = {name.upper().removesuffix("_R.TIF") for name in filenames
                       if name.upper().endswith("_R.TIF")}
        for name in filenames:
            match = re.search(r"_([A-Z0-9]{4})_([IHRLS])\.tif$", name, re.IGNORECASE)
            if not match or match[1].upper() not in supported:
                continue
            code, system = (part.upper() for part in match.groups())
            if system in {"H", "L", "S"} and name.upper()[:-6] in has_rainfed:
                continue
            with rasterio.open(f"zip://{archive.resolve()}!{name}") as layer:
                if layer.crs is None or layer.crs.to_epsg() != 4326:
                    raise ValueError(f"Unexpected projection in {name}")
                arrays[code, system] = _area_grid(layer)
    areas = {}
    for code in supported:
        if (code, "I") in arrays:
            areas[code, "ir"] = arrays[code, "I"]
        if (code, "R") in arrays:
            areas[code, "rf"] = arrays[code, "R"]
        elif all((code, mode) in arrays for mode in ("H", "L", "S")):
            areas[code, "rf"] = sum(arrays[code, mode] for mode in ("H", "L", "S"))
    return areas


def _file_table(path: Path, areas: dict[tuple[str, str], np.ndarray]) -> pd.DataFrame:
    code, system = GGCMI_FILENAME.fullmatch(path.name).groups()
    with xr.open_dataset(path, decode_timedelta=False) as dataset:
        print(f"{path.name}: {', '.join(dataset.data_vars)}")
        for variable, units in (("planting_day", "day of year"), ("maturity_day", "day of year"),
                                ("growing_season_length", "days")):
            if dataset[variable].attrs.get("units") != units:
                raise ValueError(f"Unexpected units for {variable} in {path.name}")
        planting = dataset.planting_day.transpose("lat", "lon").values
        maturity = dataset.maturity_day.transpose("lat", "lon").values
        lengths = dataset.growing_season_length.transpose("lat", "lon").values
        lat_idx, lon_idx = np.where(
            (planting >= 1) & (planting <= 365) & (maturity >= 1) & (maturity <= 365)
            & (lengths > 0) & (lengths <= 365)
        )
        lat = dataset.lat.values[lat_idx]
        lon = ((dataset.lon.values[lon_idx] + 180) % 360) - 180
        rows, cols = _grid_indices(lat, lon)
        flags = dataset.data_source_used.transpose("lat", "lon").values[lat_idx, lon_idx]
        source = pd.Series(flags).astype("Int16").astype("string").radd("GGCMI source ")
        area = areas.get((SPAM_CODES.get(code), system))
        fraction = np.full(len(lat), np.nan, dtype=np.float32)
        if area is not None:
            fraction = (area[rows, cols] / AREA_ROW[rows]).astype(np.float32)
            source = source.fillna("GGCMI calendar").str.cat(
                pd.Series(" + MapSPAM 2010 area", index=source.index))
            if "fraction_of_harvested_area" in dataset:
                rice_share = dataset.fraction_of_harvested_area.transpose("lat", "lon").values[lat_idx, lon_idx]
                fraction *= rice_share
        return pd.DataFrame(dict(lat=lat.astype("float32"), lon=lon.astype("float32"),
                                 crop_code=code, system=system,
                                 plant_doy=planting[lat_idx, lon_idx].astype("int16"),
                                 maturity_doy=maturity[lat_idx, lon_idx].astype("int16"),
                                 season_len=lengths[lat_idx, lon_idx].astype("int16"),
                                 harvested_frac=fraction, data_source=source), columns=COLUMNS)


def main():
    parser = argparse.ArgumentParser(description="Build GGCMI v1.01 calendars with MapSPAM 2010 local harvested area")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--mapspam", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output", type=Path, default=DATA / "ggcmi" / "ggcmi_cells.parquet")
    options = parser.parse_args()
    if options.download:
        calendars, default_archive = fetch_sources(options.input_dir)
    else:
        calendars = [path for path in options.input_dir.glob("*.nc4") if GGCMI_FILENAME.fullmatch(path.name)]
        default_archive = options.input_dir / SPAM_NAME
    if not calendars:
        parser.error("No GGCMI version 1.01 calendars found")
    archive = options.mapspam or default_archive
    if not archive.is_file():
        parser.error("MapSPAM 2010 harvested-area archive required to verify crop presence")
    areas = harvested_areas(archive, set(SPAM_CODES.values()))
    if not areas:
        parser.error("No supported MapSPAM 2010 harvested-area layers found")
    frames = [_file_table(path, areas) for path in sorted(calendars)]
    table = pd.concat(frames, ignore_index=True).sort_values(["lat", "lon", "system", "crop_code"])
    options.output.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(options.output, index=False, compression="zstd", row_group_size=90_000)
    print(f"Crop codes: {', '.join(sorted(table.crop_code.unique()))}")
    print(f"{len(table):,} calendar rows, {options.output.stat().st_size / 1_000_000:.2f} MB")


if __name__ == "__main__":
    main()
