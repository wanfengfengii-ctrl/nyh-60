import math
from typing import List, Tuple, Optional
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


def rpm_to_flow_rate(rpm: float, config: WellConfig) -> float:
    if rpm <= 0 or config.pulley_radius_m <= 0 or config.well_depth_m <= 0:
        return 0.0
    angular_speed = rpm * 2 * math.pi / 60
    linear_speed = angular_speed * config.pulley_radius_m
    if linear_speed <= 0:
        return 0.0
    time_per_bucket_s = config.well_depth_m / linear_speed
    if time_per_bucket_s <= 0:
        return 0.0
    flow_rate_lpm = (config.bucket_capacity_l / time_per_bucket_s) * 60
    return round(flow_rate_lpm, 2)


def flow_rate_to_rpm(flow_rate_lpm: float, config: WellConfig) -> float:
    if flow_rate_lpm <= 0 or config.bucket_capacity_l <= 0 or config.well_depth_m <= 0:
        return 0.0
    liters_per_second = flow_rate_lpm / 60
    buckets_per_second = liters_per_second / config.bucket_capacity_l
    if buckets_per_second <= 0:
        return 0.0
    time_per_bucket_s = 1 / buckets_per_second
    linear_speed = config.well_depth_m / time_per_bucket_s
    if config.pulley_radius_m <= 0:
        return 0.0
    angular_speed = linear_speed / config.pulley_radius_m
    rpm = angular_speed * 60 / (2 * math.pi)
    return round(rpm, 2)


def predict_efficiency(
    config: WellConfig,
    target_rpm: Optional[float] = None,
    historical_rpms: Optional[List[float]] = None
) -> dict:
    rpms = [r for r in (historical_rpms or []) if r and r > 0]
    avg_historical_rpm = sum(rpms) / len(rpms) if rpms else 15.0
    effective_rpm = target_rpm if target_rpm and target_rpm > 0 else avg_historical_rpm

    flow_rate_lpm = rpm_to_flow_rate(effective_rpm, config)
    liters_per_hour = round(flow_rate_lpm * 60, 2)

    if effective_rpm > 0 and config.pulley_radius_m > 0:
        angular_speed = effective_rpm * 2 * math.pi / 60
        linear_speed = angular_speed * config.pulley_radius_m
        time_per_bucket_s = round(config.well_depth_m / linear_speed, 2) if linear_speed > 0 else 0.0
    else:
        time_per_bucket_s = 0.0

    bucket_cycles_per_minute = round(flow_rate_lpm / config.bucket_capacity_l, 2) if config.bucket_capacity_l > 0 else 0.0

    if len(rpms) >= 3:
        variance = sum((r - avg_historical_rpm) ** 2 for r in rpms) / len(rpms)
        std_dev = math.sqrt(variance)
        cv = std_dev / avg_historical_rpm if avg_historical_rpm > 0 else 1
        confidence = round(max(0.5, min(0.98, 1.0 - cv * 0.5)), 2)
    elif len(rpms) >= 1:
        confidence = 0.7
    else:
        confidence = 0.5

    return {
        "predicted_flow_rate_lpm": flow_rate_lpm,
        "predicted_time_per_bucket_s": time_per_bucket_s,
        "predicted_liters_per_hour": liters_per_hour,
        "target_rpm": round(effective_rpm, 2),
        "bucket_cycles_per_minute": bucket_cycles_per_minute,
        "confidence": confidence,
        "factors": {
            "well_depth_m": config.well_depth_m,
            "bucket_capacity_l": config.bucket_capacity_l,
            "bucket_diameter_m": config.bucket_diameter_m,
            "pulley_radius_m": config.pulley_radius_m,
            "historical_sample_count": len(rpms),
            "historical_avg_rpm": round(avg_historical_rpm, 2)
        }
    }


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


def recalculate_experiment(experiment: Experiment, config: WellConfig) -> Experiment:
    total_time, total_water, flow_rate, avg_speed, speed_curve = calculate_experiment_efficiency(experiment, config)
    experiment.total_time_s = total_time
    experiment.total_water_l = total_water
    experiment.flow_rate_lpm = flow_rate
    experiment.avg_speed_rpm = avg_speed
    for i, tp in enumerate(experiment.time_points):
        if i < len(speed_curve):
            tp.calculated_speed_rpm = speed_curve[i]["rpm"]
    return experiment


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
