import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from basalt.climate.power import fetch_power, write_climate
from basalt.config import DEMO, DEMO_COORDS, ROOT, SCOPE
from basalt.explain.cards import render_stability
from basalt.satellite.ornl import fetch_modis_et, fetch_ndvi
from basalt.service import precompute_demo


def write_json(path: Path, value, *, compact: bool = False) -> None:
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=None if compact else 2,
                         separators=(",", ":") if compact else None)
    scratch = path.with_suffix(".tmp")
    scratch.write_text(payload + "\n", encoding="utf-8")
    scratch.replace(path)


def summarize(bundle: dict) -> dict:
    story = bundle["field_story"]
    return {
        "site": story["site"], "scope": SCOPE, "tier": story["tier"],
        "current_rotation": next(row["name"] for row in bundle["evidence"] if row["is_current"]),
        "calendar_source": story["calendar_source"], "field_patterns": story["patterns"],
        "validations": bundle["validation"], "lever_rejections": bundle["rejections"],
        "datasets": list(dict.fromkeys(dataset for row in bundle["evidence"] for dataset in row["datasets"])),
        "options": [
            {"rotation_id": row["rotation_id"], "name": row["name"], "lever": row["lever"], "verdict": row["verdict"],
             "arrows": row["arrows"], "wins": row["wins_vs_current"], "stability": row["stability"],
             "stability_line": render_stability(row), "medians": {
                 metric: row["metrics"][metric]["median"] for metric in
                 ("soil_score", "et_mm", "irr_gross_mm", "risk_hits", "bare_days")
             }} for row in bundle["evidence"]
        ],
    }


def fetch_modis(site_id: str) -> None:
    _, lat, lon = DEMO_COORDS[site_id]
    destination = DEMO / site_id
    destination.mkdir(parents=True, exist_ok=True)
    for name, fetch in (("ndvi", fetch_ndvi), ("modis_et", fetch_modis_et)):
        observations = fetch(lat, lon, timeout=60)
        target = destination / f"{name}.parquet"
        scratch = target.with_suffix(".tmp")
        observations.to_parquet(scratch)
        scratch.replace(target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the eight network-free basalt demos and the results summary")
    parser.add_argument("--fetch-power", action="store_true", help="Update the checked NASA POWER weather input")
    parser.add_argument("--fetch-modis", action="store_true", help="Update the ORNL greenness and water-use composites")
    opts = parser.parse_args()
    if opts.fetch_modis:
        with ThreadPoolExecutor(max_workers=2) as executor:
            tuple(executor.map(fetch_modis, DEMO_COORDS))
    summary = {}
    for site_id, (_, lat, lon) in DEMO_COORDS.items():
        destination = DEMO / site_id
        destination.mkdir(parents=True, exist_ok=True)
        if opts.fetch_power:
            write_climate(fetch_power(lat, lon), destination / "climate.parquet")
        bundle = precompute_demo(site_id)
        write_json(destination / "bundle.json", bundle, compact=True)
        summary[site_id] = summarize(bundle)
    write_json(ROOT / "results_summary.json", summary)


if __name__ == "__main__":
    main()
