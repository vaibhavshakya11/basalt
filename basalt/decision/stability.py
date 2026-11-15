from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from basalt.config import YEARS
from basalt.contracts import ClimateTable, Constraints, Crop, ModelParameters, Rotation, RotationRun, Site, Soil, Stability
from basalt.decision.replay import compare_runs, copy_templates, replay_runs
from basalt.physics.soilhealth import FACTORS, score

SOIL_ORDER = ("sand", "loamy_sand", "sandy_loam", "loam", "silt_loam", "clay_loam", "clay")


def _change_crops(crops: Mapping[str, Crop], change: Callable[[Crop], Crop]) -> dict[str, Crop]:
    return {crop_id: change(crop) for crop_id, crop in crops.items()}


def _rice(crop: Crop) -> bool:
    return crop.ponded


def _wheat(crop: Crop) -> bool:
    return crop.crop_id.startswith("wheat")


def _heat(crop: Crop) -> bool:
    return crop.tcrit_heat_c is not None


def _with_weights(runs: Mapping[str, RotationRun], weights: tuple[float, ...]) -> dict[str, RotationRun]:
    return {
        rotation_id: replace(run, seasons=tuple(
            replace(season, soil_score=score(season.soil_factors, weights)) for season in run.seasons
        ))
        for rotation_id, run in runs.items()
    }


def stability(
    site: Site, climate: ClimateTable, rotations: Sequence[Rotation], crops: Mapping[str, Crop],
    soil: Soil, soils: Mapping[str, Soil], constraints: Constraints = Constraints(),
    *, baseline: Mapping[str, RotationRun] | None = None, years: Sequence[int] = YEARS,
) -> dict[str, Stability]:
    """Identify every tested assumption endpoint that changes an option's arrows."""
    defaults = ModelParameters()
    baseline = baseline or replay_runs(site, climate, rotations, crops, soil, constraints, years=years)
    base_arrows = compare_runs(baseline, site.irrigated)
    tested = {rotation_id: [] for rotation_id in baseline}
    rotation_crops = {
        rotation.rotation_id: tuple(crops[slot.crop_id] for group in rotation.years for slot in group)
        for rotation in rotations
    }
    labels = copy_templates()["stability_drivers"]

    def evaluate(param: str, runs: Mapping[str, RotationRun], threshold: int = 16) -> None:
        arrows = compare_runs(runs, site.irrigated, threshold)
        for rotation_id, candidate_arrows in arrows.items():
            if candidate_arrows != base_arrows[rotation_id] and param not in tested[rotation_id]:
                tested[rotation_id].append(param)

    def run_test(
        param: str, *, parameters=defaults, perturbed_crops=crops,
        perturbed_soil=soil, shift_days=0, touches: Callable[[Crop], bool] | None = None,
    ) -> None:
        reuse = {
            rotation_id: baseline[rotation_id]
            for rotation_id, selected in rotation_crops.items()
            if touches is not None and not any(touches(crop) for crop in selected)
        }
        if len(reuse) == len(rotations):
            return
        runs = replay_runs(site, climate, rotations, perturbed_crops, perturbed_soil, constraints,
                           parameters=parameters, shift_days=shift_days, years=years, reuse=reuse)
        evaluate(param, runs)

    if site.irrigated:
        for value in (2, 15):
            run_test("rice_percolation", parameters=replace(defaults, rice_percolation=value), touches=_rice)
        for value in (0.50, 0.75):
            run_test("irrigation_efficiency", parameters=replace(defaults, irrigation_efficiency=value))
    for value in (0.3, 0.7):
        perturbed = _change_crops(crops, lambda crop: replace(crop, kc_ini=value) if _wheat(crop) else crop)
        run_test("wheat_kc_ini", perturbed_crops=perturbed, touches=_wheat)
    for shift in (-1, 1):
        perturbed = _change_crops(crops, lambda crop: replace(crop, tcrit_heat_c=crop.tcrit_heat_c + shift) if _heat(crop) else crop)
        run_test("heat_threshold", perturbed_crops=perturbed, touches=_heat)
    for shift in (-14, 14):
        run_test("sowing_date", shift_days=shift)
    for multiplier in (0.75, 1.25):
        perturbed = _change_crops(crops, lambda crop: replace(crop, zr_max_m=max(crop.zr_min_m, crop.zr_max_m * multiplier)))
        run_test("root_depth", perturbed_crops=perturbed)
    soil_index = SOIL_ORDER.index(site.soil_class)
    for neighbor in (soil_index - 1, soil_index + 1):
        if 0 <= neighbor < len(SOIL_ORDER) and SOIL_ORDER[neighbor] in soils:
            run_test("soil_class", perturbed_soil=soils[SOIL_ORDER[neighbor]])
    for shift in (-7, 7):
        run_test("burn_window", parameters=replace(defaults, burn_days_shift=shift))
    for factor_index, factor in enumerate(FACTORS):
        for multiplier in (0.5, 1.5):
            weights = tuple(multiplier if index == factor_index else 1.0 for index in range(len(FACTORS)))
            evaluate(f"soil_weight_{factor}", _with_weights(baseline, weights))
    for value in (14, 18):
        evaluate("arrow_threshold", baseline, value)

    return {
        rotation_id: Stability(
            badge="depends" if drivers else "robust",
            drivers=[{"param": param, "label": labels[param]["label"]} for param in drivers],
        )
        for rotation_id, drivers in tested.items()
    }
