import math
from typing import List, Tuple
from models import Experiment, TimePoint, WellConfig


def calculate_speed_at_point(
    curr_water_l: float,
    prev_water_l: float,
    curr_time_s: float,
    prev_time_s: float,
    config: WellConfig
) -> float:
    delta_water = curr_water_l - prev_water_l
    delta_time = curr_time_s - prev_time_s

    if delta_time <= 0 or delta_water <= 0:
        return 0.0

    if config.bucket_capacity_l <= 0 or config.pulley_radius_m <= 0:
        return 0.0

    bucket_cycles = delta_water / config.bucket_capacity_l
    rope_distance = bucket_cycles * config.well_depth_m

    linear_speed = rope_distance / delta_time

    angular_speed = linear_speed / config.pulley_radius_m
    rpm = angular_speed * 60 / (2 * math.pi)

    return round(rpm, 2)


def calculate_experiment_efficiency(experiment: Experiment, config: WellConfig) -> Tuple[float, float, float, float, List[dict]]:
    points = sorted(experiment.time_points, key=lambda p: p.point_index)

    if len(points) < 2:
        return 0.0, 0.0, 0.0, 0.0, []

    total_time_s = points[-1].time_s - points[0].time_s
    total_water_l = points[-1].water_l - points[0].water_l

    if total_water_l > config.bucket_capacity_l:
        total_water_l = config.bucket_capacity_l

    if total_time_s <= 0:
        total_time_s = 0.001

    flow_rate_lpm = (total_water_l / total_time_s) * 60

    speed_curve = []
    rpm_values = []

    for i in range(len(points)):
        if i == 0:
            rpm = 0.0
        else:
            rpm = calculate_speed_at_point(
                points[i].water_l, points[i - 1].water_l,
                points[i].time_s, points[i - 1].time_s,
                config
            )
        speed_curve.append({
            "point_index": points[i].point_index,
            "time_s": points[i].time_s,
            "water_l": points[i].water_l,
            "rpm": rpm
        })
        rpm_values.append(rpm)

    valid_rpms = [r for r in rpm_values if r > 0]
    avg_speed_rpm = sum(valid_rpms) / len(valid_rpms) if valid_rpms else 0.0

    return (
        round(total_time_s, 2),
        round(total_water_l, 2),
        round(flow_rate_lpm, 2),
        round(avg_speed_rpm, 2),
        speed_curve
    )


def detect_anomalies(experiments: List[Experiment]) -> None:
    flow_rates = [e.flow_rate_lpm for e in experiments if e.flow_rate_lpm and e.review_status == "valid"]
    if len(flow_rates) < 2:
        for exp in experiments:
            exp.is_abnormal = False
        return

    avg = sum(flow_rates) / len(flow_rates)
    threshold = avg * 0.5

    for exp in experiments:
        if exp.flow_rate_lpm and exp.review_status == "valid":
            exp.is_abnormal = exp.flow_rate_lpm < threshold
        else:
            exp.is_abnormal = False


def mark_experiments_for_review(experiments: List[Experiment]) -> None:
    for exp in experiments:
        exp.review_status = "pending_review"
