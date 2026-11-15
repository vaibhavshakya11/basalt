from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ET0Terms:
    ra: np.ndarray
    rso: np.ndarray
    rn: np.ndarray
    et0: np.ndarray


def saturation_vapor_pressure(temperature_c):
    """Return kPa from temperature in degrees Celsius, FAO-56 Eq. 11."""
    temperature_c = np.asarray(temperature_c)
    return 0.6108 * np.exp(17.27 * temperature_c / (temperature_c + 237.3))


def pressure_from_elevation(elevation_m):
    """Return kPa from elevation in metres, FAO-56 Eq. 7."""
    return 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26


def extraterrestrial_radiation(lat, day_of_year):
    """Return MJ/m²/day, FAO-56 Eqs. 21–25."""
    latitude = np.deg2rad(lat)
    orbit = 2 * np.pi * np.asarray(day_of_year) / 365
    distance = 1 + 0.033 * np.cos(orbit)
    declination = 0.409 * np.sin(orbit - 1.39)
    sunset = np.arccos(np.clip(-np.tan(latitude) * np.tan(declination), -1, 1))
    radiation = (
        sunset * np.sin(latitude) * np.sin(declination)
        + np.cos(latitude) * np.cos(declination) * np.sin(sunset)
    )
    return np.maximum((24 * 60 / np.pi) * 0.0820 * distance * radiation, 0)


def hargreaves(tmax, tmin, ra):
    """Return mm/day, FAO-56 Eq. 52 with Ra converted to equivalent mm/day."""
    tmax, tmin = np.asarray(tmax), np.asarray(tmin)
    mean_temperature = (tmax + tmin) / 2
    return np.maximum(0.0023 * (mean_temperature + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0)) * 0.408 * ra, 0)


def penman_monteith(*, tmax, tmin, ws2, rs, ps, lat, elevation_m, day_of_year, tdew=None, rh=None, ea=None):
    """Return daily FAO-56 Eq. 6 ET0 and its radiation terms."""
    tmax, tmin, ws2, rs, ps = (np.asarray(column) for column in (tmax, tmin, ws2, rs, ps))
    mean_temperature = (tmax + tmin) / 2
    gamma = 0.000665 * ps
    es = (saturation_vapor_pressure(tmax) + saturation_vapor_pressure(tmin)) / 2
    if ea is None:
        dew_vapor_pressure = saturation_vapor_pressure(np.nan if tdew is None else tdew)
        rh_vapor_pressure = np.asarray(np.nan if rh is None else rh) / 100 * es
        ea = np.where(np.isnan(dew_vapor_pressure), rh_vapor_pressure, dew_vapor_pressure)
    slope = 4098 * saturation_vapor_pressure(mean_temperature) / (mean_temperature + 237.3) ** 2
    ra = extraterrestrial_radiation(lat, day_of_year)
    rso = (0.75 + 2e-5 * elevation_m) * ra
    radiation_ratio = np.divide(rs, rso, out=np.zeros_like(ra + rs, dtype=float), where=rso > 0)
    rns = 0.77 * rs
    rnl = (
        4.903e-9 * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2
        * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * np.minimum(radiation_ratio, 1) - 0.35)
    )
    rn = rns - rnl
    et0 = (
        (0.408 * slope * rn + gamma * 900 / (mean_temperature + 273) * ws2 * (es - ea))
        / (slope + gamma * (1 + 0.34 * ws2))
    )
    et0 = np.where(np.isnan(rs), hargreaves(tmax, tmin, ra), np.maximum(et0, 0))
    return ET0Terms(ra, rso, rn, et0)


def reference_et0(table):
    """Calculate a daily ET0 series using the climate table's source metadata."""
    return penman_monteith(
        **{name: table[name].to_numpy() for name in ("tmax", "tmin", "tdew", "rh", "ws2", "rs", "ps")},
        lat=table.attrs["lat"],
        elevation_m=table.attrs["elevation_m"],
        day_of_year=table.index.dayofyear.to_numpy(),
    ).et0


def example_18() -> ET0Terms:
    """Evaluate the FAO-56 worked example at Brussels on July 6."""
    return penman_monteith(
        tmax=21.5, tmin=12.3, ea=1.409, ws2=2.078, rs=22.07,
        ps=pressure_from_elevation(100), lat=50.8, elevation_m=100, day_of_year=187,
    )
