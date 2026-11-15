from functools import lru_cache
from pathlib import Path

import pandas as pd

from basalt.calendar_utils import doy_month_day
from basalt.config import DATA
from basalt.contracts import CropSlot, LocalCalendar

TABLE = DATA / "ggcmi" / "ggcmi_cells.parquet"
CROP_CODES = {
    "mai": "maize", "ri1": "rice", "ri2": "rice",
    "swh": "wheat_spring", "wwh": "wheat_winter", "soy": "soybean",
    "nut": "groundnut", "bea": "beans", "pea": "pea", "sor": "sorghum",
    "mil": "millet", "cot": "cotton", "rap": "rapeseed",
}
MIN_HARVESTED_FRACTION = 0.01
COLUMNS = (
    "lat", "lon", "crop_code", "system", "plant_doy", "maturity_doy",
    "season_len", "harvested_frac", "data_source",
)


def ggcmi_cell(lat: float, lon: float) -> tuple[float, float]:
    """Return the containing half-degree cell centre, including antimeridian wrapping."""
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Location must be between 90° S and 90° N, 180° W and 180° E")
    cell_lat = min(int((lat + 90) * 2), 359) / 2 - 89.75
    cell_lon = int(((lon + 180) % 360) * 2) / 2 - 179.75
    return cell_lat, cell_lon


@lru_cache(maxsize=1024)
def _rows(path: Path, lat: float, lon: float, system: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError("The GGCMI calendar table is unavailable")
    return pd.read_parquet(path, columns=list(COLUMNS),
                           filters=[("lat", "==", lat), ("lon", "==", lon), ("system", "==", system)])


def local_calendars(lat: float, lon: float, irrigated: bool, *, grown_only: bool = True,
                    path: Path = TABLE) -> tuple[LocalCalendar, ...]:
    """Read supported calendars for one cell and production system."""
    cell_lat, cell_lon = ggcmi_cell(lat, lon)
    rows = _rows(path, cell_lat, cell_lon, "ir" if irrigated else "rf")
    calendars = []
    for row in rows.itertuples():
        if row.crop_code not in CROP_CODES:
            continue
        fraction = None if pd.isna(row.harvested_frac) else float(row.harvested_frac)
        source = None if pd.isna(row.data_source) else str(row.data_source)
        if grown_only and (fraction is None or fraction < MIN_HARVESTED_FRACTION):
            continue
        calendars.append(LocalCalendar(CROP_CODES[row.crop_code], row.system, int(row.plant_doy),
                                       int(row.maturity_doy), int(row.season_len), fraction, source,
                                       row.crop_code))
    return tuple(sorted(calendars, key=lambda calendar: (-(calendar.harvested_frac or 0), calendar.crop_code)))


def calendar_slot(calendar: LocalCalendar) -> CropSlot:
    return CropSlot(calendar.crop_id, doy_month_day(calendar.plant_doy),
                    doy_month_day(calendar.maturity_doy))


def default_season_start(calendar: LocalCalendar) -> str:
    planting_month = int(doy_month_day(calendar.plant_doy)[:2])
    return f"{(planting_month - 3) % 12 + 1:02d}-01"
