import argparse
from hashlib import sha256
from io import BytesIO
from itertools import product
from math import cos, radians
import os
from pathlib import Path
from time import monotonic, sleep

import pandas as pd
import requests

from basalt.config import DATA, DEMO_COORDS

APPEEARS = "https://appeears.earthdatacloud.nasa.gov/api"
PRODUCT = "SPL4SMGP.008"
LAYER = "Geophysical_Data_sm_rootzone_wetness"


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
        "task_name": "Basalt Malawi SMAP root zone",
        "params": {
            "dates": [{"startDate": "04-01-2015", "endDate": "12-31-2024"}],
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
        if status not in {"pending", "processing"}:
            raise RuntimeError(f"AppEEARS task {task_id} returned {status}")
        if monotonic() >= deadline:
            raise TimeoutError(f"Resume AppEEARS task with --task-id {task_id}")
        sleep(min(30, max(0, deadline - monotonic())))


def daily_wetness(samples: list[pd.DataFrame]) -> pd.DataFrame:
    records = []
    for frame in samples:
        layer = next((column for column in frame if column.endswith(LAYER)), None)
        day = next((column for column in ("Date", "date", "DateTime") if column in frame), None)
        if day is None or layer is None:
            raise ValueError("AppEEARS sample is missing the date or root-zone wetness column")
        dates = pd.to_datetime(frame[day], format="mixed", utc=True).dt.tz_localize(None).dt.normalize()
        value = pd.to_numeric(frame[layer], errors="coerce")
        records.append(pd.DataFrame({"date": dates, "sm_rootzone_wetness": value.where(value.between(0, 1))}))
    combined = pd.concat(records, ignore_index=True)
    combined = combined.loc[combined["date"].between("2015-04-01", "2024-12-31")]
    return combined.groupby("date", as_index=False).mean().dropna()


def _download_samples(session, task_id, files):
    samples = []
    for metadata in files["files"]:
        filename = metadata["file_name"].lower()
        if not filename.endswith(".csv") or PRODUCT.lower() not in filename or "statistics" in filename:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build daily SMAP L4 root-zone wetness for central Malawi")
    parser.add_argument("--task-id", help="Resume an existing AppEEARS point task")
    parser.add_argument("--wait-minutes", type=int, default=20)
    parser.add_argument("--csv", type=Path, nargs="+", help="Process point CSVs already downloaded from AppEEARS")
    parser.add_argument("--output", type=Path, default=DATA / "smap" / "malawi_smap_l4.parquet")
    options = parser.parse_args()
    if options.csv:
        frames = [pd.read_csv(path) for path in options.csv]
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
    options.output.parent.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(options.output, index=False, compression="zstd")
    print(f"Wrote {len(daily):,} daily values from {daily.date.min():%Y-%m-%d} to {daily.date.max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
