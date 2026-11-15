import argparse
from pathlib import Path
from shutil import copyfile

from kaleido import write_fig_sync

from basalt.config import ROOT
from basalt.service import load_demo
from basalt.ui.strata import strata_figure


def export_strata(destination: Path) -> None:
    """Export the computed Ludhiana current rotation with full event labels."""
    demo = load_demo("ludhiana")
    current = demo["field_story"]["current_rotation_id"]
    figure = strata_figure(demo["strata"][current], include_legend=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_fig_sync(figure, path=destination, opts={"format": "png", "width": 1440})


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the real Ludhiana Season Strata as a PNG.")
    parser.add_argument("--destination", type=Path, default=ROOT / "docs" / "season-strata.png")
    parser.add_argument("--review-copy", type=Path, default=ROOT / "review" / "screenshots" / "10_strata_ludhiana.png")
    args = parser.parse_args()
    export_strata(args.destination)
    args.review_copy.parent.mkdir(parents=True, exist_ok=True)
    if args.review_copy.resolve() != args.destination.resolve():
        copyfile(args.destination, args.review_copy)


if __name__ == "__main__":
    main()
