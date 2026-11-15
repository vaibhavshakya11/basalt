import numpy as np

from basalt.contracts import Crop

COVER_FACTOR = {"bare": 1., "ini": .6, "dev": .3, "mid": .1, "late": .1}


def crop_events(crop: Crop, stage: np.ndarray, tmax: np.ndarray,
                tmin: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    flowering = np.zeros(len(stage), dtype=bool)
    flowering[np.flatnonzero(stage == "mid")[:15]] = True
    heat = flowering & (tmax >= crop.tcrit_heat_c) if crop.tcrit_heat_c is not None else np.zeros_like(flowering)
    frost = (tmin <= crop.frost_tmin_c) if crop.frost_sensitive else np.zeros_like(flowering)
    if crop.frost_window == "mid_first_15d":
        frost &= flowering
    return heat, frost


def burn_pressure(residue: str, gap_days: int, machinery: bool, threshold_shift: int = 0) -> float:
    base = 1. if gap_days <= 21 + threshold_shift else .5 if gap_days <= 35 + threshold_shift else .15
    load = {"high": 1., "medium": .5, "low": 0., "none": 0.}[residue]
    return base * load * (.3 if machinery else 1.)


def erosion(rain: np.ndarray, stages: np.ndarray, covered_bare: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """RUSLE daily rain proxy without a slope factor."""
    significant = rain >= 12.7
    covers = np.array([COVER_FACTOR[stage] for stage in stages])
    covers[covered_bare] = .4
    return np.where(significant, rain ** 1.81 * covers, 0.), significant & (stages == "bare")
