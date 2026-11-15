from dataclasses import dataclass

CURVE_NUMBERS = {"A": (67, 77), "B": (78, 86), "C": (85, 91), "D": (89, 94)}


@dataclass(frozen=True)
class WaterDay:
    dr: float
    pond: float
    ks: float
    et: float
    runoff: float
    net: float
    gross: float
    drainage: float
    residual: float


def runoff_mm(rain: float, cn: float, wet: bool = False) -> float:
    """USDA TR-55 curve-number runoff, in mm."""
    if wet:
        cn = 23 * cn / (10 + 0.13 * cn)
    storage = 25400 / cn - 254
    excess = max(0., rain - 0.2 * storage)
    return excess * excess / (excess + storage)


def readily_available(taw: float, p: float, etc: float) -> float:
    return taw * max(0.1, min(0.8, p + 0.04 * (5 - etc)))


def root_day(dr: float, taw: float, raw: float, rain: float, etc: float,
             cn: float, irrigation: float, efficiency: float, pond: float = 0.) -> WaterDay:
    """FAO-56 Eq. 85, with ET limited to the water actually available."""
    runoff = runoff_mm(rain, cn, dr < 0.1 * taw)
    inputs = rain - runoff + irrigation + pond
    pre_et_dr = max(0., dr - inputs)
    ks = 1. if pre_et_dr <= raw else (taw - pre_et_dr) / (taw - raw)
    et = min(etc * ks, taw - dr + inputs)
    drainage = max(0., inputs - et - dr)
    final = max(0., min(taw, dr - inputs + et + drainage))
    residual = final - dr + pond - (et + drainage + runoff - rain - irrigation)
    return WaterDay(final, 0., ks, et, runoff, irrigation, irrigation / efficiency, drainage, residual)


def rice_day(dr: float, taw: float, raw: float, pond: float, rain: float, etc: float,
             irrigation: float, percolation: float) -> WaterDay:
    """Use the bunded surface store first and the root store once the pond empties."""
    surface = pond + rain + irrigation
    recharge = min(dr, surface)
    pre_et_dr = dr - recharge
    surface -= recharge
    ks = 1. if surface > 0 or pre_et_dr <= raw else (taw - pre_et_dr) / (taw - raw)
    et = min(etc * ks, taw - pre_et_dr + surface)
    from_pond = min(et, surface)
    final = pre_et_dr + et - from_pond
    surface -= from_pond
    drainage = min(percolation, surface)
    surface -= drainage
    runoff = max(0., surface - 150.)
    surface -= runoff
    residual = final - dr + pond - surface - (et + drainage + runoff - rain - irrigation)
    return WaterDay(final, surface, ks, et, runoff, irrigation, irrigation, drainage, residual)


def rice_refill(pond: float, age: int, dry_days: int, days_left: int) -> float:
    if days_left < 14:
        return 0.
    if age < 14 and pond < 20.:
        return 50. - pond
    if dry_days >= 2 and pond == 0.:
        return 75.
    return 0.
