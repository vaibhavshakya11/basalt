from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEMO = DATA / "demo"
CACHE = DATA / "cache"
YEARS = tuple(range(2001, 2025))
PUNJAB_BOUNDS = (73.8, 29.5, 77.0, 32.6)
SLIDES_URL = "?view=slides"
SCOPE = (
    "Runs for any cultivated region covered by the global datasets. Calibrated in Punjab "
    "(with Punjab Agricultural University guidance); global defaults elsewhere, "
    "with the accuracy cost measured and confidence always shown."
)
DEMO_COORDS = {
    "ludhiana": ("Ludhiana, Punjab, India", 30.80, 75.70),
    "malawi": ("Central Malawi (Lilongwe plain)", -13.80, 33.45),
    "jaipur": ("Jaipur, Rajasthan, India", 26.880, 75.582),
    "fresno": ("Fresno County, California, United States", 36.664, -119.950),
    "cordoba": ("Córdoba, Andalusia, Spain", 37.92, -4.68),
    "toowoomba": ("Toowoomba, Queensland, Australia", -27.477, 151.801),
    "sinop": ("Sinop, Mato Grosso, Brazil", -11.918, -55.552),
    "damanhur": ("Damanhur, Nile Delta, Egypt", 30.74, 30.48),
}
DEMO_PROFILES = {
    "ludhiana": {
        "label": "Ludhiana, India", "region": "Punjab",
        "summary": "Irrigated rice and wheat give you a way to compare groundwater pumping and a switch away from ponded rice.",
        "teaser": "Explore how irrigated rice and wheat compare with a maize rotation.",
        "crop_ids": ("pb_rw",), "irrigated": True,
    },
    "malawi": {
        "label": "Lilongwe plain, Malawi", "region": "Central Malawi",
        "summary": "Rainfed maize lets you explore whether a legume or a different crop sequence changes dry-season stress.",
        "teaser": "Explore how rainfed maize compares with a rotation that includes a legume.",
        "crop_ids": ("maize",), "irrigated": False,
    },
    "jaipur": {
        "label": "Jaipur, India", "region": "Rajasthan",
        "summary": "Rainfed millet shows how a rotation can be constrained by a short monsoon and a long dry season.",
        "crop_ids": ("millet",), "irrigated": False,
    },
    "fresno": {
        "label": "Fresno County, United States", "region": "California",
        "summary": "Irrigated cotton offers a summer crop comparison where rainfall timing and irrigation demand can diverge.",
        "crop_ids": ("cotton",), "irrigated": True,
    },
    "cordoba": {
        "label": "Córdoba, Spain", "region": "Andalusia",
        "summary": "Rainfed winter wheat shows how a crop can use the cooler, wetter months before the Mediterranean summer.",
        "crop_ids": ("wheat_winter",), "irrigated": False,
    },
    "toowoomba": {
        "label": "Toowoomba, Australia", "region": "Queensland",
        "summary": "Rainfed sorghum adds a Southern Hemisphere summer cereal and lets you compare options exposed to dry spells.",
        "crop_ids": ("sorghum",), "irrigated": False,
    },
    "sinop": {
        "label": "Sinop, Brazil", "region": "Mato Grosso",
        "summary": "Rainfed soybean and maize show how two crops can share one rainy season and leave different amounts of time for soil cover.",
        "crop_ids": ("soybean", "maize"), "irrigated": False,
    },
    "damanhur": {
        "label": "Damanhur, Egypt", "region": "Nile Delta",
        "summary": "Irrigated wheat and maize illustrate a two-crop year in which rainfall supplies little of the water crops use.",
        "crop_ids": ("wheat_spring", "maize"), "irrigated": True,
    },
}


def in_punjab(lat: float, lon: float) -> bool:
    west, south, east, north = PUNJAB_BOUNDS
    return south <= lat <= north and west <= lon <= east
