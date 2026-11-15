from basalt.climate.et0 import reference_et0
from basalt.contracts import ClimateTable, Scenario


def apply_scenario(table: ClimateTable, scenario: Scenario) -> ClimateTable:
    """Apply a temperature and rainfall perturbation relative to the baseline."""
    if not 0 <= scenario.dT_c <= 3 or not 0.7 <= scenario.rain_mult <= 1.3:
        raise ValueError("The climate scenario is outside the supported range.")
    if table.attrs.get("scenario_dT", 0) == scenario.dT_c and table.attrs.get("scenario_rain_mult", 1) == scenario.rain_mult:
        return table
    shifted = table.copy()
    shifted[["tmax", "tmin", "tdew"]] += scenario.dT_c - table.attrs.get("scenario_dT", 0)
    shifted["precip"] *= scenario.rain_mult / table.attrs.get("scenario_rain_mult", 1)
    shifted.attrs.update(scenario_dT=scenario.dT_c, scenario_rain_mult=scenario.rain_mult)
    shifted["et0"] = reference_et0(shifted)
    return shifted
