from functools import lru_cache
from math import isclose
from pathlib import Path
from typing import Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, TypeAdapter

from basalt.calendar_utils import validate_rotation
from basalt.contracts import Crop, Rotation, Soil, SoilClass

T = TypeVar("T")
KNOWLEDGE = Path(__file__).resolve().parent
TAGS = frozenset({
    "nitrogen_fixing", "cover", "deep_rooting", "drought_tolerant",
    "fodder_value", "extra_harvest",
})


def read_yaml(name: str) -> dict:
    with (KNOWLEDGE / name).open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a mapping")
    return value


def validated(value, schema: type[T]) -> T:
    return TypeAdapter(schema).validate_python(value)


class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str
    parameter: str
    value: str
    source: Literal["assumption"]
    confidence: Literal["L"]
    reason: str


def _validate_crop(crop: Crop) -> None:
    if (crop.stage_days is None) == (crop.stage_fracs is None):
        raise ValueError(f"{crop.crop_id}: define either stage lengths or stage fractions")
    if crop.stage_days is not None and (min(crop.stage_days) < 0 or sum(crop.stage_days) <= 0):
        raise ValueError(f"{crop.crop_id}: invalid stage lengths")
    if crop.stage_fracs is not None and (min(crop.stage_fracs) < 0 or not isclose(sum(crop.stage_fracs), 1, abs_tol=0.0100001)):
        raise ValueError(f"{crop.crop_id}: stage fractions must sum to approximately one")
    if not 0 < crop.zr_min_m <= crop.zr_max_m or not 0 < crop.p < 1:
        raise ValueError(f"{crop.crop_id}: invalid rooting or depletion parameters")
    if not set(crop.tags) <= TAGS or not set(crop.confidence.values()) <= {"H", "M", "L"}:
        raise ValueError(f"{crop.crop_id}: invalid tags or confidence")
    if any(low > high for low, high in crop.ranges.values()):
        raise ValueError(f"{crop.crop_id}: range low exceeds range high")


@lru_cache(maxsize=1)
def _crop_library() -> dict[str, Crop]:
    raw_crops = read_yaml("crops.yaml")
    raw_gaps = read_yaml("gap_crops.yaml")
    sections = (raw_crops["calibrated_punjab"], raw_crops["global"], raw_gaps["gap_crops"])
    crops = {}
    for section in sections:
        for crop_id, fields in section.items():
            if crop_id in crops:
                raise ValueError(f"Crop ID is duplicated: {crop_id}")
            optional = dict.fromkeys(("stage_days", "stage_fracs", "tbase_c", "gdd_req", "min_window_days"))
            crop = validated({"crop_id": crop_id, **optional, **fields}, Crop)
            _validate_crop(crop)
            crops[crop_id] = crop
    for crop_id in raw_gaps["gap_crops"]:
        gap = crops[crop_id]
        if gap.tbase_c is None or not gap.gdd_req or not gap.min_window_days:
            raise ValueError(f"{crop_id}: missing thermal screening parameters")
    if not set(load_ggcmi_codes().values()) <= set(raw_crops["global"]):
        raise ValueError("GGCMI code maps to an undefined global crop")
    return crops


def load_crops() -> dict[str, Crop]:
    """Load the calibrated, global, and gap crop parameters by ID."""
    return _crop_library().copy()


def load_ggcmi_codes() -> dict[str, str]:
    """Map the calendar file crop codes to basalt crop IDs."""
    return validated(read_yaml("crops.yaml")["ggcmi_codes"], dict[str, str])


@lru_cache(maxsize=1)
def _soil_library() -> dict[SoilClass, Soil]:
    soils = validated(read_yaml("soils.yaml")["soils"], dict[SoilClass, Soil])
    for soil_class, soil in soils.items():
        if not 0 < soil.theta_wp < soil.theta_fc <= 1 or soil.rice_percolation <= 0:
            raise ValueError(f"{soil_class}: invalid water retention or percolation")
    return soils


def load_soils() -> dict[SoilClass, Soil]:
    """Load water retention and percolation for each soil texture."""
    return _soil_library().copy()


@lru_cache(maxsize=1)
def _punjab_library() -> dict[str, Rotation]:
    raw = read_yaml("rotations_punjab.yaml")
    crops = load_crops()
    rotations = {}
    for rotation_id, fields in raw["rotations"].items():
        rotation = validated({"rotation_id": rotation_id, **fields}, Rotation)
        validate_rotation(rotation, crops, raw["season_year_start"])
        rotations[rotation_id] = rotation
    if sum(rotation.is_current for rotation in rotations.values()) != 1:
        raise ValueError("Punjab presets require one current rotation")
    return rotations


def load_punjab_rotations() -> dict[str, Rotation]:
    """Load Punjab rotation presets and check gaps across seasons."""
    return _punjab_library().copy()


@lru_cache(maxsize=1)
def load_assumptions() -> tuple[Assumption, ...]:
    """Return the low-confidence inputs added to parameterize the model."""
    assumptions = [row for name in ("crops.yaml", "gap_crops.yaml", "soils.yaml") for row in read_yaml(name)["assumptions"]]
    return validated(assumptions, tuple[Assumption, ...])


def bare_depletion_fraction() -> float:
    """Return the low-confidence stress threshold for bare soil."""
    value = float(next(entry.value for entry in load_assumptions() if entry.parameter == "bare_depletion_fraction"))
    if not 0 < value < 1:
        raise ValueError("Bare soil depletion fraction must be strictly between zero and one")
    return value
