import argparse
from hashlib import sha256
from io import BytesIO
from itertools import product
from math import cos, radians
import os
from pathlib import Path
import re
from time import monotonic, sleep
from zipfile import ZipFile

import pandas as pd
import requests

from basalt.config import DATA, DEMO_COORDS

APPEEARS = "https://appeears.earthdatacloud.nasa.gov/api"
PRODUCT = "SPL4SMGP.008"
LAYER = "Geophysical_Data_sm_rootzone_wetness"
START_DATE = "2015-04-01"
END_DATE = "2024-12-31"
RESULT_FILE = re.compile(r"(?:^|[._-])spl4smgp[._-]008[._-]results\.csv$", re.IGNORECASE)


def _payload() -> dict:
    _, latitude, longitude = DEMO_COORDS["malawi"]
    degrees_lat = 1 / 111.195
    degrees_lon = degrees_lat / cos(radians(latitude))
    points = [
        {
            "id": str(index),
            "latitude": round(latitude + dy * degrees_lat, 6),
            "longitude": round(longitude + dx * degrees_lon, 6),
        }
        for index, (dy, dx) in enumerate(product((-1, 0, 1), repeat=2))
    ]
    return {
        "task_type": "point",
        "task_name": "basalt Malawi SMAP root zone",
        "params": {
            "dates": [{"startDate": "04-01-2015", "endDate": "12-31-2024", "recurring": False}],
            "layers": [{"product": PRODUCT, "layer": LAYER}],
            "coordinates": points,
        },
    }


def _open_session() -> requests.Session:
    username = os.environ.get("EARTHDATA_USERNAME")
    password = os.environ.get("EARTHDATA_PASSWORD")
    if not username or not password:
        raise ValueError("Set EARTHDATA_USERNAME and EARTHDATA_PASSWORD in the local environment")
    login = requests.post(f"{APPEEARS}/login", auth=(username, password), timeout=45)
    login.raise_for_status()
    session = requests.Session()
    session.headers["Authorization"] = "Bearer " + login.json()["token"]
    return session


def _bundle(session: requests.Session, task_id: str, wait_minutes: int) -> dict:
    deadline = monotonic() + wait_minutes * 60
    while True:
        response = session.get(f"{APPEEARS}/task/{task_id}", timeout=45)
        response.raise_for_status()
        status = response.json()["status"]
        if status == "done":
            files = session.get(f"{APPEEARS}/bundle/{task_id}", timeout=45)
            files.raise_for_status()
            return files.json()
        if status not in {"pending", "queued", "processing"}:
            raise RuntimeError(f"AppEEARS task {task_id} returned {status}")
        if monotonic() >= deadline:
            raise TimeoutError(f"Resume AppEEARS task with --task-id {task_id}")
        sleep(min(30, max(0, deadline - monotonic())))


def daily_wetness(samples: list[pd.DataFrame]) -> pd.DataFrame:
    expected_points = {(point["latitude"], point["longitude"]) for point in _payload()["params"]["coordinates"]}
    records = []
    for frame in samples:
        columns = {column.strip().lower(): column for column in frame}
        layer = columns.get(f"spl4smgp_008_{LAYER.lower()}", columns.get(LAYER.lower()))
        day = next((columns[name] for name in ("datetime", "date_time", "date") if name in columns), None)
        if day is None or layer is None or not {"latitude", "longitude"}.issubset(columns):
            raise ValueError("AppEEARS results must include the date, coordinates and SMAP version 8 root-zone wetness")
        timestamps = frame[day]
        if day == columns.get("date") and "time" in columns:
            timestamps = timestamps.astype(str) + " " + frame[columns["time"]].astype(str)
        dates = pd.to_datetime(timestamps, format="mixed", utc=True).dt.tz_localize(None).dt.normalize()
        latitude = pd.to_numeric(frame[columns["latitude"]]).round(6)
        longitude = pd.to_numeric(frame[columns["longitude"]]).round(6)
        value = pd.to_numeric(frame[layer], errors="coerce")
        records.append(pd.DataFrame({"date": dates, "latitude": latitude, "longitude": longitude,
                                     "sm_rootzone_wetness": value.where(value.between(0, 1))}))
    combined = pd.concat(records, ignore_index=True)
    combined = combined.loc[combined["date"].between(START_DATE, END_DATE)]
    coordinates = combined[["latitude", "longitude"]].drop_duplicates()
    if set(coordinates.itertuples(index=False, name=None)) != expected_points:
        raise ValueError("AppEEARS results must cover the nine requested Malawi points")
    # Average each point's three-hour samples first so missing values do not change spatial weights.
    point_daily = combined.groupby(["date", "latitude", "longitude"])["sm_rootzone_wetness"].mean()
    return point_daily.groupby("date").mean().dropna().reset_index()


def _download_samples(session, task_id, files):
    samples = []
    for metadata in files["files"]:
        if not RESULT_FILE.search(metadata["file_name"]):
            continue
        response = session.get(f"{APPEEARS}/bundle/{task_id}/{metadata['file_id']}", timeout=120)
        response.raise_for_status()
        checksum = metadata.get("sha256")
        if checksum and sha256(response.content).hexdigest() != checksum:
            raise ValueError(f"Checksum mismatch for {metadata['file_name']}")
        samples.append(pd.read_csv(BytesIO(response.content)))
    if not samples:
        raise RuntimeError(f"No {PRODUCT} point CSVs in AppEEARS bundle {task_id}")
    return samples


def _bundle_samples(path: Path) -> list[pd.DataFrame]:
    with ZipFile(path) as bundle:
        names = [name for name in bundle.namelist() if RESULT_FILE.search(Path(name).name)]
        if not names:
            raise ValueError(f"No {PRODUCT} point results CSV in {path.name}")
        frames = []
        for name in names:
            with bundle.open(name) as stream:
                frames.append(pd.read_csv(stream))
        return frames


def main() -> None:
    parser = argparse.ArgumentParser(description="Build daily SMAP L4 root-zone wetness for central Malawi")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--task-id", help="Resume an existing AppEEARS point task")
    inputs.add_argument("--csv", type=Path, nargs="+", help="Process point results CSVs downloaded from AppEEARS")
    inputs.add_argument("--bundle", type=Path, nargs="+", help="Process point ZIP bundles downloaded from AppEEARS")
    parser.add_argument("--wait-minutes", type=int, default=20)
    parser.add_argument("--output", type=Path, default=DATA / "smap" / "malawi_smap_l4.parquet")
    options = parser.parse_args()
    if options.csv:
        frames = [pd.read_csv(path) for path in options.csv]
    elif options.bundle:
        frames = [frame for path in options.bundle for frame in _bundle_samples(path)]
    else:
        with _open_session() as session:
            task_id = options.task_id
            if task_id is None:
                response = session.post(f"{APPEEARS}/task", json=_payload(), timeout=45)
                response.raise_for_status()
                task_id = response.json()["task_id"]
                print(f"AppEEARS task {task_id}", flush=True)
            files = _bundle(session, task_id, options.wait_minutes)
            frames = _download_samples(session, task_id, files)
    daily = daily_wetness(frames)
    if daily.empty:
        raise ValueError("No valid SMAP days in the requested interval")
    if daily.date.min() != pd.Timestamp(START_DATE) or daily.date.max() != pd.Timestamp(END_DATE):
        raise ValueError(f"AppEEARS results must span {START_DATE} to {END_DATE}")
    daily.attrs.update({
        "source": "NASA AppEEARS point sample",
        "product": PRODUCT,
        "layer": LAYER,
        "timestamp_zone": "UTC",
        "sample_points": _payload()["params"]["coordinates"],
        "aggregation": "Mean per day at each point, followed by the mean across points.",
    })
    options.output.parent.mkdir(parents=True, exist_ok=True)
    staging = options.output.with_suffix(".tmp")
    daily.to_parquet(staging, index=False, compression="zstd")
    staging.replace(options.output)
    print(f"Wrote {len(daily):,} daily values from {daily.date.min():%Y-%m-%d} to {daily.date.max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
