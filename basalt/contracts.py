from dataclasses import dataclass
from typing import Literal, TypedDict

import numpy as np
import pandas as pd

ClimateTable = pd.DataFrame
Tier = Literal["calibrated", "global"]
SoilClass = Literal["sand", "loamy_sand", "sandy_loam", "loam", "silt_loam", "clay_loam", "clay"]
Lever = Literal["current", "fill_the_gap", "swap_weak_link", "take_turns", "combine"]
Arrow = Literal["better", "similar", "worse"]
CLIMATE_UNITS = {
    "tmax": "°C", "tmin": "°C", "tdew": "°C", "rh": "%", "ws2": "m/s",
    "rs": "MJ/m²/day", "precip": "mm/day", "ps": "kPa", "et0": "mm/day", "qc_filled": "bool",
}


@dataclass(frozen=True)
class Site:
    site_id: str
    name: str
    lat: float
    lon: float
    tier: Tier
    soil_class: SoilClass
    soil_source: Literal["soilgrids", "user", "demo_default"]
    irrigated: bool
    season_year_start: str
    ggcmi_cell: tuple[float, float] | None = None


@dataclass(frozen=True)
class Crop:
    crop_id: str
    name: str
    family: str
    kc_ini: float
    kc_mid: float
    kc_end: float
    stage_fracs: tuple[float, float, float, float] | None
    stage_days: tuple[int, int, int, int] | None
    zr_min_m: float
    zr_max_m: float
    p: float
    height_m: float
    ponded: bool
    tcrit_heat_c: float | None
    heat_window: str
    frost_sensitive: bool
    frost_tmin_c: float
    frost_window: str
    residue: Literal["high", "medium", "low", "none"]
    tags: tuple[str, ...]
    tbase_c: float | None
    gdd_req: float | None
    min_window_days: int | None
    sources: tuple[str, ...]
    confidence: dict[str, str]
    ranges: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class Soil:
    theta_fc: float
    theta_wp: float
    hydrologic_group: Literal["A", "B", "C", "D"]
    rice_percolation: float
    confidence: Literal["H", "M", "L"]
    source: str


@dataclass(frozen=True)
class CropSlot:
    crop_id: str
    sow: str
    harvest: str | None = None


@dataclass(frozen=True)
class Rotation:
    rotation_id: str
    name: str
    lever: Lever
    cycle_years: Literal[1, 2]
    years: tuple[tuple[CropSlot, ...], ...]
    is_current: bool
    notes: str


@dataclass(frozen=True)
class Constraints:
    irrigations_per_year_max: int | None = None
    has_residue_machinery: bool = False
    prefer_assured_market: bool = False


@dataclass(frozen=True)
class Priorities:
    soil: float = 1
    water: float = 1
    risk: float = 1


@dataclass(frozen=True)
class Scenario:
    dT_c: float = 0.0
    rain_mult: float = 1.0


@dataclass(frozen=True)
class DailyState:
    crop_id: np.ndarray
    stage: np.ndarray
    kc: np.ndarray
    etc: np.ndarray
    etc_adj: np.ndarray
    ks: np.ndarray
    dr_mm: np.ndarray
    taw_mm: np.ndarray
    rain: np.ndarray
    runoff: np.ndarray
    irr_net: np.ndarray
    irr_gross: np.ndarray
    deep_perc: np.ndarray
    pond_mm: np.ndarray
    heat_event: np.ndarray
    frost_event: np.ndarray
    erosive_bare_event: np.ndarray
    dry_stress_event: np.ndarray


@dataclass(frozen=True)
class SeasonResult:
    season: int
    et_mm: float
    irr_net_mm: float
    irr_gross_mm: float
    irr_events: int
    rain_mm: float
    runoff_mm: float
    deep_perc_mm: float
    heat_days: int
    heat_hit_crops: int
    frost_days: int
    frost_hit_crops: int
    dry_stress_frac: float
    dry_hit_crops: int
    risk_hits: int
    bare_days: int
    erosion_index: float
    burn_pressure: float
    soil_factors: dict[str, float]
    soil_score: float
    wb_residual_max_mm: float
    irr_exceeds_limit: bool


@dataclass(frozen=True)
class SeasonRun:
    season: int
    dates: pd.DatetimeIndex
    daily: DailyState
    result: SeasonResult


@dataclass(frozen=True)
class RotationRun:
    rotation: Rotation
    seasons: tuple[SeasonResult, ...]
    phases: tuple[tuple[SeasonRun, ...], ...]


class Metric(TypedDict):
    median: float
    p10: float
    p90: float
    unit: str
    direction: Literal["higher_better", "lower_better", "context"]


class Wins(TypedDict):
    better: int
    worse: int
    tie: int


class StabilityDriver(TypedDict):
    param: str
    label: str


class Stability(TypedDict):
    badge: Literal["robust", "depends"]
    drivers: list[StabilityDriver]


class CalendarEvidence(TypedDict):
    crop_id: str
    sow_doy: int
    harvest_doy: int
    year_in_cycle: int


class Evidence(TypedDict):
    rotation_id: str
    name: str
    lever: Lever
    is_current: bool
    site_id: str
    tier: Tier
    scenario: dict[str, float]
    n_seasons: int
    season_range: list[int]
    metrics: dict[str, Metric | dict[str, Metric]]
    wins_vs_current: dict[str, Wins]
    arrows: dict[str, Arrow]
    verdict: str
    stability: Stability
    constraints_flags: list[str]
    tags: list[str]
    calendar: list[CalendarEvidence]
    why: list[str]
    gaps: list[str]
    risks: list[str]
    datasets: list[str]
    sources: list[str]
    assumptions_L: list[str]


class FieldStory(TypedDict):
    site: dict
    tier: Tier
    current_rotation_id: str
    ndvi_seasons_detected: int
    calendar_source: Literal["ndvi", "ggcmi", "pau"]
    patterns: list[dict]
    trends: list[dict]
    grace: dict


class ValidationResult(TypedDict):
    check_id: str
    site: str
    dataset: str
    version: str
    period: str
    n: int
    metric: str
    value: float | dict | None
    unit: str
    pass_rule: str
    status: Literal["pass", "caveat", "fail", "not_run"]
    note: str
    figure_path: str | None


@dataclass(frozen=True)
class ModelParameters:
    rice_percolation: float | None = None
    irrigation_efficiency: float = 0.60
    puddling_mm: float = 200
    burn_days_shift: int = 0
    soil_weights: tuple[float, ...] = (1, 1, 1, 1, 1, 1)


@dataclass(frozen=True)
class CropWindow:
    crop: Crop
    sow: pd.Timestamp
    harvest: pd.Timestamp
    season: int
    stage_days: tuple[int, int, int, int]


@dataclass(frozen=True)
class LocalCalendar:
    crop_id: str
    system: Literal["ir", "rf"]
    plant_doy: int
    maturity_doy: int
    season_len: int
    harvested_frac: float | None
    data_source: str | None
    crop_code: str
