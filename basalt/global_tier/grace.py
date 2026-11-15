from functools import lru_cache
from pathlib import Path

import numpy as np

from basalt.config import DATA
from basalt.global_tier.ggcmi import ggcmi_cell

TABLE = DATA / "grace" / "grace_trend.npz"
GLOBAL_TABLE = DATA / "grace" / "grace_global.npz"
JPL_DATASET = "GRACE/GRACE-FO NASA JPL RL06.3Mv04"
GSFC_DATASET = "GRACE/GRACE-FO NASA Goddard (catalog RL06v2.0)"
UNAVAILABLE = "Regional water storage data are unavailable for this location."


@lru_cache(maxsize=2)
def read_grace_grid(path: Path = TABLE) -> dict:
    with np.load(path, allow_pickle=False) as payload:
        grid = {name: payload[name] for name in payload.files}
    if grid["trend_cm_per_yr"].shape != (len(grid["lat"]), len(grid["lon"])):
        raise ValueError("GRACE trend grid dimensions do not match the coordinates")
    return grid


def _trend_at(real_lat: float, real_lon: float, path: Path) -> dict | None:
    if not path.is_file():
        return None
    grid = read_grace_grid(path)
    rows = np.flatnonzero(np.isclose(grid["lat"], real_lat, rtol=0))
    cols = np.flatnonzero(np.isclose((grid["lon"] + 180) % 360 - 180, real_lon, rtol=0))
    if not rows.size or not cols.size:
        return None
    trend = float(grid["trend_cm_per_yr"][rows[0], cols[0]])
    if not np.isfinite(trend):
        return None
    period = f"{grid['period_start'].item()} to {grid['period_end'].item()}"
    dataset = str(grid["dataset"].item()) if "dataset" in grid else JPL_DATASET
    detail = str(grid["source_detail"].item()) if "source_detail" in grid else ""
    return {
        "trend_cm_per_yr": trend, "period": period,
        "dataset": dataset,
        "note": ("Total water stored on land. The satellite measurement covers about 300 km. "
                 f"{detail}").strip(),
    }


def regional_trend(lat: float, lon: float, *, path: Path = TABLE, fallback: Path = GLOBAL_TABLE) -> dict:
    """Return the land-water trend, preferring the JPL record for the demo cells."""
    cell_lat, cell_lon = ggcmi_cell(lat, lon)
    return (_trend_at(cell_lat, cell_lon, path) or _trend_at(cell_lat, cell_lon, fallback)
            or {"trend_cm_per_yr": None, "period": None, "note": UNAVAILABLE})
