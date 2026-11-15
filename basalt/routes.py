from dataclasses import dataclass
from math import isfinite
from typing import Literal, Mapping, Sequence

from basalt.config import DEMO_COORDS

ROUTE_FIELDS = ("view", "site", "lat", "lon")


@dataclass(frozen=True)
class Route:
    kind: Literal["landing", "slides", "demo", "pin", "invalid"]
    site: str | None = None
    coordinates: tuple[float, float] | None = None
    error: str | None = None

    @property
    def key(self) -> str:
        if self.coordinates is not None:
            lat, lon = self.coordinates
            return f"pin_{lat:.6f}_{lon:.6f}"
        return self.site or self.kind


def parse_route(query: Mapping[str, Sequence[str]]) -> Route:
    """Resolve application links and reject ambiguous or incomplete locations."""
    entries = {key: query[key] for key in ROUTE_FIELDS if key in query}
    if any(len(values) != 1 for values in entries.values()):
        return Route("invalid", error="invalid_link")
    values = {key: items[0].strip() for key, items in entries.items()}
    if "view" in values:
        return Route("slides") if values == {"view": "slides"} else Route("invalid", error="invalid_link")
    if "site" in values:
        site = values["site"].lower()
        if len(values) != 1:
            return Route("invalid", error="invalid_link")
        return Route("demo", site=site) if site in DEMO_COORDS else Route("invalid", error="invalid_demo")
    if not values:
        return Route("landing")
    try:
        lat, lon = (float(values[key]) for key in ("lat", "lon"))
    except (KeyError, ValueError, OverflowError):
        return Route("invalid", error="invalid_location")
    if not (isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return Route("invalid", error="invalid_location")
    return Route("pin", coordinates=(lat or 0., (-180. if lon == 180 else lon) or 0.))
