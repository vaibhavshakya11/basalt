import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from math import floor, isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep

import requests
from PIL import Image

from basalt.config import CACHE
from basalt.contracts import SoilClass

WCS = "https://maps.isric.org/mapserv"
WGS84 = "http://www.opengis.net/def/crs/EPSG/0/4326"
DEPTHS = (("0-5cm", 5), ("5-15cm", 10), ("15-30cm", 15))
PROPERTIES = ("sand", "silt", "clay")


class SoilGridsUnavailable(RuntimeError):
    """No usable soil texture estimate could be fetched for this pin."""


def texture_class(sand: float, silt: float, clay: float) -> SoilClass:
    """Classify the grain fractions with the USDA texture triangle."""
    total = sand + silt + clay
    if not all(isfinite(fraction) and fraction >= 0 for fraction in (sand, silt, clay)) or total <= 0:
        raise ValueError("Soil texture fractions must be finite and sum to a positive value")
    sand, silt, clay = (fraction * 100 / total for fraction in (sand, silt, clay))
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 2 * clay < 30:
        return "loamy_sand"
    if (7 <= clay < 20 and sand > 52 and silt + 2 * clay >= 30) or (clay < 7 and silt < 50 and silt + 2 * clay >= 30):
        return "sandy_loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (50 <= silt and 12 <= clay < 27) or (50 <= silt and clay < 12):
        return "silt_loam"
    if (20 <= clay < 35 and silt < 28 and sand > 45) or (27 <= clay < 40 and sand <= 45) or (27 <= clay < 40 and silt >= 40):
        return "clay_loam"
    return "clay"


def _coverage_query(property_name: str, depth: str, lat: float, lon: float) -> list[tuple[str, str]]:
    radius = 0.003
    return [
        ("map", f"/map/{property_name}.map"),
        ("SERVICE", "WCS"),
        ("VERSION", "2.0.1"),
        ("REQUEST", "GetCoverage"),
        ("COVERAGEID", f"{property_name}_{depth}_mean"),
        ("FORMAT", "GEOTIFF_INT16"),
        ("SUBSETTINGCRS", WGS84),
        ("OUTPUTCRS", WGS84),
        ("SUBSET", f"Lat({max(-90, lat - radius):.6f},{min(90, lat + radius):.6f})"),
        ("SUBSET", f"Long({max(-180, lon - radius):.6f},{min(180, lon + radius):.6f})"),
    ]


def _sample_geotiff(coverage: bytes, lat: float, lon: float) -> int:
    with Image.open(BytesIO(coverage)) as raster:
        if raster.format != "TIFF" or raster.width > 20 or raster.height > 20:
            raise ValueError("Unexpected dimensions or encoding in SoilGrids coverage")
        scale_x, scale_y, _ = raster.tag_v2[33550]
        origin_col, origin_row, _, origin_lon, origin_lat, _ = raster.tag_v2[33922]
        col = floor(origin_col + (lon - origin_lon) / scale_x)
        row = floor(origin_row + (origin_lat - lat) / scale_y)
        if not (0 <= row < raster.height and 0 <= col < raster.width):
            raise ValueError("Pin is outside the SoilGrids coverage")
        fraction = raster.getpixel((col, row))
        if not isinstance(fraction, int) or not 0 <= fraction <= 1000:
            raise ValueError("SoilGrids coverage has no grain fraction at the pin")
        return fraction


def _fetch_fraction(property_name: str, depth: str, lat: float, lon: float) -> int:
    query = _coverage_query(property_name, depth, lat, lon)
    for attempt in range(3):
        try:
            response = requests.get(WCS, params=query, timeout=8, allow_redirects=False)
            response.raise_for_status()
            return _sample_geotiff(response.content, lat, lon)
        except (requests.RequestException, OSError, ValueError, KeyError) as error:
            if attempt == 2:
                raise SoilGridsUnavailable(f"Could not read {property_name} at {depth} from SoilGrids") from error
            sleep(0.25 * (2 ** attempt))
    raise AssertionError("All SoilGrids requests were attempted")


def write_soil_json(path: Path, soil: dict) -> None:
    """Write a complete soil record without exposing a partial cache entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        json.dump(soil, stream, indent=2, allow_nan=False)
        stream.write("\n")
    temp.replace(path)


def fetch_soilgrids(lat: float, lon: float, *, cache_dir: Path = CACHE / "soilgrids") -> dict:
    """Fetch and depth-weight WCS texture estimates for a field pin."""
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Latitude or longitude outside its valid range")
    cached = cache_dir / f"{lat:.2f}_{lon:.2f}.json"
    if cached.is_file():
        soil = json.loads(cached.read_text(encoding="utf-8"))
        if soil["coverage_unit"] != "g/kg" or soil["unit"] != "%":
            raise ValueError("SoilGrids cache has unexpected units")
        return soil

    with ThreadPoolExecutor(max_workers=9) as workers:
        pending = {
            (prop, depth): workers.submit(_fetch_fraction, prop, depth, lat, lon)
            for prop in PROPERTIES
            for depth, _ in DEPTHS
        }
        by_depth = {
            prop: {depth: pending[prop, depth].result() for depth, _ in DEPTHS}
            for prop in PROPERTIES
        }
    weighted = {
        prop: sum(by_depth[prop][depth] * weight for depth, weight in DEPTHS) / 30
        for prop in PROPERTIES
    }
    total = sum(weighted.values())
    if total <= 0:
        raise SoilGridsUnavailable("SoilGrids grain fractions are all zero")
    percentages = {prop: fraction * 100 / total for prop, fraction in weighted.items()}
    soil = dict(soil_class=texture_class(**percentages), source="soilgrids", **percentages,
                unit="%", coverage_unit="g/kg", depth_cm=[0, 30], lat=lat, lon=lon,
                coverage_g_kg=by_depth, dataset="SoilGrids 2.0 via WCS")
    write_soil_json(cached, soil)
    return soil
