from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEMO = DATA / "demo"
CACHE = DATA / "cache"
YEARS = tuple(range(2001, 2025))
PUNJAB_BOUNDS = (73.8, 29.5, 77.0, 32.6)
SLIDES_URL = "SLIDES_URL_TBD"
SCOPE = (
    "Runs for any cultivated region covered by the global datasets. Calibrated in Punjab "
    "(with Punjab Agricultural University guidance); global defaults elsewhere, "
    "with the accuracy cost measured and confidence always shown."
)
DEMO_COORDS = {
    "ludhiana": ("Ludhiana, Punjab, India", 30.80, 75.70),
    "malawi": ("Central Malawi (Lilongwe plain)", -13.80, 33.45),
}


def in_punjab(lat: float, lon: float) -> bool:
    west, south, east, north = PUNJAB_BOUNDS
    return south <= lat <= north and west <= lon <= east
