from collections.abc import Iterable

import numpy as np

FACTORS = ("living_cover", "residue_kept", "legume_months",
           "no_puddling", "pest_cycle_break", "erosive_rain_bare")


def soil_factors(bare: int, burn: float, legumes: int, puddled: bool,
                 families: Iterable[str], erosion: float, erosion_ref: float) -> dict[str, float]:
    diversity = (0., .6, 1.)[min(2, max(0, len(set(families)) - 1))]
    erosion_loss = min(1., erosion / erosion_ref) if erosion_ref > 0 else float(erosion > 0)
    values = (max(0., 1 - bare / 365), 1 - burn, min(1., legumes / 120),
              float(not puddled), diversity, 1 - erosion_loss)
    return dict(zip(FACTORS, values, strict=True))


def score(factors: dict[str, float], weights: tuple[float, ...]) -> float:
    return float(100 * np.average([factors[key] for key in FACTORS], weights=weights))
