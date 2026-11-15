import argparse
from concurrent.futures import ThreadPoolExecutor

from basalt.config import DEMO, DEMO_COORDS
from basalt.soil.soilgrids import fetch_soilgrids, write_soil_json


def fetch_site(site_id: str) -> tuple[str, str]:
    _, lat, lon = DEMO_COORDS[site_id]
    soil = fetch_soilgrids(lat, lon)
    write_soil_json(DEMO / site_id / "soil.json", soil)
    return site_id, soil["soil_class"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Get 0 to 30 cm SoilGrids texture for the demo pins.")
    parser.add_argument("sites", nargs="*", choices=tuple(DEMO_COORDS), default=None)
    options = parser.parse_args()
    with ThreadPoolExecutor(max_workers=2) as workers:
        for site, soil_class in workers.map(fetch_site, options.sites or DEMO_COORDS):
            print(f"{site}: {soil_class}")


if __name__ == "__main__":
    main()
