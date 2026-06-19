import math
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
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


def calculate_labor_instantaneous_flows(time_points: list) -> List[float]:
    flows = []
    for i in range(len(time_points)):
        if i == 0:
            flows.append(0.0)
        else:
            prev_tp = time_points[i - 1]
            curr_tp = time_points[i]
            dt = curr_tp.elapsed_min - prev_tp.elapsed_min
            dw = curr_tp.total_water_l - prev_tp.total_water_l
            if dt > 0 and not curr_tp.is_rest_period:
                flow = dw / dt
            else:
                flow = 0.0
            flows.append(round(flow, 4))
    return flows


def detect_labor_anomalies(time_points: list, flows: List[float]) -> List[dict]:
    anomalies = []
    valid_flows = [f for f in flows if f > 0]
    if len(valid_flows) < 3:
        return anomalies

    mean_flow = sum(valid_flows) / len(valid_flows)
    variance = sum((f - mean_flow) ** 2 for f in valid_flows) / len(valid_flows)
    std_flow = math.sqrt(variance) if variance > 0 else 0.001

    for i, flow in enumerate(flows):
        if flow <= 0:
            continue
        z_score = abs(flow - mean_flow) / std_flow if std_flow > 0 else 0
        if z_score > 2.5:
            anomalies.append({
                "point_index": i,
                "elapsed_min": time_points[i].elapsed_min,
                "flow_lpm": flow,
                "type": "flow_spike" if flow > mean_flow else "flow_drop",
                "z_score": round(z_score, 2),
                "description": f"在{time_points[i].elapsed_min}min处出水量{'偏高' if flow > mean_flow else '偏低'}，偏离均值{round(z_score, 1)}倍标准差"
            })

    for i in range(1, len(time_points)):
        prev_w = time_points[i - 1].total_water_l
        curr_w = time_points[i].total_water_l
        if curr_w < prev_w:
            anomalies.append({
                "point_index": i,
                "elapsed_min": time_points[i].elapsed_min,
                "type": "water_decrease",
                "description": f"累计出水量异常下降（{prev_w}L -> {curr_w}L）"
            })

    return anomalies


def calculate_labor_peak_info(flows: List[float], time_points: list) -> Tuple[float, float, float]:
    if not flows or len(flows) < 2:
        return 0.0, 0.0, 0.0

    valid_flows = [(i, f) for i, f in enumerate(flows) if f > 0]
    if not valid_flows:
        return 0.0, 0.0, 0.0

    peak_idx, peak_flow = max(valid_flows, key=lambda x: x[1])

    valid_indices = sorted([i for i, f in enumerate(flows) if f > 0])
    peak_threshold = peak_flow * 0.8

    start_idx = peak_idx
    while start_idx > 0 and flows[start_idx - 1] >= peak_threshold:
        start_idx -= 1

    end_idx = peak_idx
    while end_idx < len(flows) - 1 and flows[end_idx + 1] >= peak_threshold:
        end_idx += 1

    peak_start = time_points[start_idx].elapsed_min if start_idx < len(time_points) else 0
    peak_end = time_points[end_idx].elapsed_min if end_idx < len(time_points) else 0
    peak_duration = max(0.0, peak_end - peak_start)

    return round(peak_flow, 4), round(peak_duration, 2), round(peak_start, 2)


def calculate_efficiency_decay(flows: List[float]) -> float:
    valid_flows = [f for f in flows if f > 0]
    if len(valid_flows) < 4:
        return 0.0

    first_half = valid_flows[: len(valid_flows) // 2]
    second_half = valid_flows[len(valid_flows) // 2 :]

    avg_first = sum(first_half) / len(first_half) if first_half else 0
    avg_second = sum(second_half) / len(second_half) if second_half else 0

    if avg_first <= 0:
        return 0.0

    decay = ((avg_first - avg_second) / avg_first) * 100
    return round(max(0.0, min(100.0, decay)), 2)


def calculate_stability_cv(flows: List[float]) -> float:
    valid_flows = [f for f in flows if f > 0]
    if len(valid_flows) < 3:
        return 0.0

    mean_flow = sum(valid_flows) / len(valid_flows)
    if mean_flow <= 0:
        return 0.0

    variance = sum((f - mean_flow) ** 2 for f in valid_flows) / len(valid_flows)
    std_flow = math.sqrt(variance) if variance > 0 else 0
    cv = (std_flow / mean_flow) * 100
    return round(cv, 2)


def calculate_fatigue_correlation(time_points: list, flows: List[float]) -> float:
    fatigue_levels = [tp.fatigue_level for tp in time_points]
    paired = [(f, fl) for f, fl in zip(flows, fatigue_levels) if f > 0]

    if len(paired) < 4:
        return 0.0

    n = len(paired)
    flows_data = [p[0] for p in paired]
    fatigues = [p[1] for p in paired]

    mean_f = sum(flows_data) / n
    mean_fl = sum(fatigues) / n

    numerator = sum((flows_data[i] - mean_f) * (fatigues[i] - mean_fl) for i in range(n))
    denom_f = math.sqrt(sum((f - mean_f) ** 2 for f in flows_data))
    denom_fl = math.sqrt(sum((fl - mean_fl) ** 2 for fl in fatigues))

    if denom_f == 0 or denom_fl == 0:
        return 0.0

    correlation = numerator / (denom_f * denom_fl)
    return round(correlation, 4)


def calculate_labor_analysis(experiment, time_points: list) -> dict:
    flows = calculate_labor_instantaneous_flows(time_points)
    anomalies = detect_labor_anomalies(time_points, flows)

    total_water_l = time_points[-1].total_water_l if time_points else 0
    total_elapsed_min = time_points[-1].elapsed_min if time_points else 0

    rest_minutes = 0.0
    effective_intervals = []
    for i in range(1, len(time_points)):
        dt = time_points[i].elapsed_min - time_points[i - 1].elapsed_min
        if time_points[i].is_rest_period:
            rest_minutes += dt
        elif flows[i] > 0:
            effective_intervals.append((flows[i], dt))

    total_effective_min = max(0.0, total_elapsed_min - rest_minutes)

    effective_water = 0.0
    for flow, dt in effective_intervals:
        effective_water += flow * dt
    total_water_l = max(total_water_l, round(effective_water, 2))

    avg_flow = 0.0
    if total_effective_min > 0:
        avg_flow = total_water_l / total_effective_min

    worker_count = getattr(experiment, 'worker_count', 1)
    per_capita_flow = avg_flow / worker_count if worker_count > 0 and avg_flow > 0 else 0

    peak_flow, peak_duration, peak_start = calculate_labor_peak_info(flows, time_points)
    efficiency_decay = calculate_efficiency_decay(flows)
    stability_cv = calculate_stability_cv(flows)
    fatigue_corr = calculate_fatigue_correlation(time_points, flows)

    work_rest_ratio = 0.0
    if rest_minutes > 0:
        work_rest_ratio = round(total_effective_min / rest_minutes, 2)
    elif total_effective_min > 0:
        work_rest_ratio = 99.9

    anomaly_flags_list = []
    if anomalies:
        anomaly_flags_list = [a["type"] for a in anomalies]

    return {
        "total_water_l": round(total_water_l, 2),
        "total_effective_min": round(total_effective_min, 2),
        "total_rest_min": round(rest_minutes, 2),
        "avg_flow_rate_lpm": round(avg_flow, 4),
        "per_capita_flow_lpm": round(per_capita_flow, 4),
        "peak_flow_rate_lpm": peak_flow,
        "peak_duration_min": peak_duration,
        "peak_start_min": peak_start,
        "efficiency_decay_pct": efficiency_decay,
        "stability_cv": stability_cv,
        "fatigue_correlation": fatigue_corr,
        "work_rest_ratio": work_rest_ratio,
        "anomaly_flags": ",".join(anomaly_flags_list),
        "anomaly_list": anomalies,
        "instantaneous_flows": flows,
    }


def calculate_synergy_gain(single_exp: dict, multi_exp: dict) -> dict:
    single_per_capita = single_exp.get("per_capita_flow_lpm", 0)
    multi_per_capita = multi_exp.get("per_capita_flow_lpm", 0)
    single_stability = single_exp.get("stability_cv", 0) or 0.001
    multi_stability = multi_exp.get("stability_cv", 0)
    single_decay = single_exp.get("efficiency_decay_pct", 0) or 0.001
    multi_decay = multi_exp.get("efficiency_decay_pct", 0)
    single_peak_dur = single_exp.get("peak_duration_min", 0) or 0.001
    multi_peak_dur = multi_exp.get("peak_duration_min", 0)

    synergy_coefficient = 0.0
    if single_per_capita > 0:
        synergy_coefficient = round((multi_per_capita / single_per_capita), 4)

    efficiency_gain = round(synergy_coefficient - 1, 4)

    stability_improvement = round(((single_stability - multi_stability) / single_stability), 4)

    decay_improvement = round(((single_decay - multi_decay) / single_decay), 4)

    peak_extension = round(((multi_peak_dur - single_peak_dur) / single_peak_dur), 4)

    rating_weights = [
        (max(0, efficiency_gain + 0.5), 0.4, "人均效率"),
        (max(0, stability_improvement + 0.5), 0.25, "稳定性"),
        (max(0, decay_improvement + 0.5), 0.2, "抗衰减"),
        (max(0, peak_extension + 0.5), 0.15, "峰值持续"),
    ]
    overall_score = round(sum(w * s for s, w, _ in rating_weights), 4)

    conclusion_parts = []
    if efficiency_gain >= 0.2:
        conclusion_parts.append(f"协同效率提升显著，人均出水量提高{round(efficiency_gain * 100, 1)}%")
    elif efficiency_gain >= 0:
        conclusion_parts.append(f"协同效率略有提升，人均出水量提高{round(efficiency_gain * 100, 1)}%")
    else:
        conclusion_parts.append(f"协同未发挥优势，人均出水量下降{round(-efficiency_gain * 100, 1)}%")

    if stability_improvement > 0.1:
        conclusion_parts.append(f"作业稳定性提升{round(stability_improvement * 100, 1)}%")
    if decay_improvement > 0.1:
        conclusion_parts.append(f"抗疲劳衰减能力提升{round(decay_improvement * 100, 1)}%")
    if peak_extension > 0.1:
        conclusion_parts.append(f"高效作业时间延长{round(peak_extension * 100, 1)}%")

    return {
        "synergy_coefficient": synergy_coefficient,
        "efficiency_gain": efficiency_gain,
        "stability_improvement": stability_improvement,
        "stability_improvement_pct": round(stability_improvement * 100, 2),
        "anti_fatigue_improvement": decay_improvement,
        "decay_improvement_pct": round(decay_improvement * 100, 2),
        "peak_duration_extension": peak_extension,
        "peak_extension_pct": round(peak_extension * 100, 2),
        "overall_score": overall_score,
        "conclusion": "；".join(conclusion_parts) if conclusion_parts else "单人作业与协同作业各有特点，建议根据实际场景选择。"
    }


def calculate_multi_round_comparison(experiments_data: List[dict]) -> dict:
    if len(experiments_data) < 2:
        return {}

    sorted_by_workers = sorted(experiments_data, key=lambda e: e.get("worker_count", 1))

    best_per_capita_idx = 0
    best_per_capita = 0
    best_stability_idx = 0
    best_stability = float("inf")
    best_sustained_idx = 0
    best_sustained = 0

    for i, exp in enumerate(sorted_by_workers):
        analysis = exp.get("analysis_result", {}) or {}
        pc = analysis.get("per_capita_flow_lpm", 0)
        cv = analysis.get("stability_cv", 999)
        decay = analysis.get("efficiency_decay_pct", 100)
        sustained = (100 - decay) * (100 - cv if cv < 100 else 1) / 100

        if pc > best_per_capita:
            best_per_capita = pc
            best_per_capita_idx = i
        if cv < best_stability:
            best_stability = cv
            best_stability_idx = i
        if sustained > best_sustained:
            best_sustained = sustained
            best_sustained_idx = i

    recommendations = []
    if best_per_capita_idx < len(sorted_by_workers):
        e = sorted_by_workers[best_per_capita_idx]
        recommendations.append({
            "aspect": "人均效率最优",
            "recommendation": f"{e.get('worker_count', 1)}人{ e.get('work_mode', '') }模式",
            "value": f"{best_per_capita:.2f} L/min/人"
        })
    if best_stability_idx < len(sorted_by_workers):
        e = sorted_by_workers[best_stability_idx]
        recommendations.append({
            "aspect": "作业稳定性最优",
            "recommendation": f"{e.get('worker_count', 1)}人{ e.get('work_mode', '') }模式",
            "value": f"变异系数 {best_stability:.2f}%"
        })
    if best_sustained_idx < len(sorted_by_workers):
        e = sorted_by_workers[best_sustained_idx]
        recommendations.append({
            "aspect": "持续作业能力最优",
            "recommendation": f"{e.get('worker_count', 1)}人{ e.get('work_mode', '') }模式",
            "value": f"综合得分 {best_sustained:.1f}"
        })

    return {
        "sorted_experiments": [
            {
                "id": e.get("id"),
                "name": e.get("experiment_name"),
                "worker_count": e.get("worker_count", 1),
                "work_mode": e.get("work_mode"),
                "analysis": e.get("analysis_result", {}) or {}
            } for e in sorted_by_workers
        ],
        "recommendations": recommendations
    }


def calculate_scene_environment_factor(scene_config) -> float:
    base_factor = 1.0

    season_factors = {
        "春季": 1.02,
        "夏季": 0.92,
        "秋季": 1.05,
        "冬季": 0.88
    }
    season = getattr(scene_config, 'season', '春季')
    base_factor *= season_factors.get(season, 1.0)

    temp = getattr(scene_config, 'temperature_c', 20.0)
    if temp < 0:
        temp_factor = 0.85 + temp * 0.01
    elif temp < 15:
        temp_factor = 0.95 + (temp - 0) * 0.003
    elif temp < 28:
        temp_factor = 1.0
    else:
        temp_factor = max(0.7, 1.0 - (temp - 28) * 0.02)
    base_factor *= max(0.5, temp_factor)

    time_factors = {
        "清晨": 1.05,
        "上午": 1.02,
        "正午": 0.9,
        "下午": 0.95,
        "傍晚": 0.98,
        "夜间": 0.8
    }
    time_of_day = getattr(scene_config, 'time_of_day', '上午')
    base_factor *= time_factors.get(time_of_day, 1.0)

    ground_factors = {
        "干燥坚实": 1.0,
        "微湿防滑": 0.92,
        "泥泞湿滑": 0.82,
        "结冰光滑": 0.75,
        "沙石凹凸": 0.88
    }
    ground = getattr(scene_config, 'ground_condition', '干燥坚实')
    base_factor *= ground_factors.get(ground, 1.0)

    humidity = getattr(scene_config, 'humidity_pct', 50.0)
    if humidity > 70:
        humidity_factor = max(0.85, 1.0 - (humidity - 70) * 0.005)
    elif humidity < 30:
        humidity_factor = max(0.9, 1.0 - (30 - humidity) * 0.003)
    else:
        humidity_factor = 1.0
    base_factor *= humidity_factor

    wind = getattr(scene_config, 'wind_level', 0)
    wind_factor = max(0.7, 1.0 - wind * 0.025)
    base_factor *= wind_factor

    water_level = getattr(scene_config, 'water_level_m', 0.0)
    if water_level > 0:
        water_level_factor = max(0.8, 1.0 - water_level * 0.03)
    else:
        water_level_factor = 1.0
    base_factor *= water_level_factor

    return round(base_factor, 4)


def calculate_base_flow_rate(well_config, worker_count: int, work_mode: str) -> float:
    if well_config is None:
        return 15.0 * worker_count

    target_rpm = 15.0
    flow_per_worker = rpm_to_flow_rate(target_rpm, well_config)

    mode_efficiency = {
        "单人独立": 1.0,
        "双人轮流": 0.92,
        "三人交替": 0.88,
        "多人协同": 0.85,
        "自定义": 0.9
    }
    mode_factor = mode_efficiency.get(work_mode, 0.9)

    if work_mode in ["双人轮流", "三人交替"]:
        active_workers = 1
    elif work_mode == "多人协同":
        active_workers = min(worker_count, 3)
    else:
        active_workers = worker_count

    base_flow = flow_per_worker * active_workers * mode_factor
    return round(base_flow, 2)


def calculate_fatigue_rate(
    worker_count: int,
    work_mode: str,
    base_fatigue_factor: float,
    workload_intensity: str,
    env_factor: float
) -> float:
    intensity_factors = {
        "轻松": 0.6,
        "中等": 1.0,
        "较重": 1.4,
        "繁重": 1.8
    }
    intensity_factor = intensity_factors.get(workload_intensity, 1.0)

    if work_mode in ["双人轮流", "三人交替"]:
        rotation_factor = 0.6
    elif work_mode == "多人协同":
        rotation_factor = 0.75
    else:
        rotation_factor = 1.0

    fatigue_rate = base_fatigue_factor * intensity_factor * rotation_factor * (2.0 - env_factor) / 60.0

    return round(fatigue_rate, 6)


def simulate_labor_scenario(
    scene_config=None,
    labor_scheme=None,
    well_config=None,
    simulation_duration_min: float = 120.0,
    time_step_min: float = 1.0
) -> dict:
    env_factor = calculate_scene_environment_factor(scene_config) if scene_config else 1.0

    worker_count = getattr(labor_scheme, 'worker_count', 1) if labor_scheme else 1
    work_mode = getattr(labor_scheme, 'work_mode', '单人独立') if labor_scheme else '单人独立'
    continuous_duration_min = getattr(labor_scheme, 'continuous_duration_min', 30.0) if labor_scheme else 30.0
    rest_interval_min = getattr(labor_scheme, 'rest_interval_min', 0.0) if labor_scheme else 0.0
    rest_duration_min = getattr(labor_scheme, 'rest_duration_min', 5.0) if labor_scheme else 5.0
    shift_rotation = getattr(labor_scheme, 'shift_rotation', False) if labor_scheme else False
    shift_duration_min = getattr(labor_scheme, 'shift_duration_min', 15.0) if labor_scheme else 15.0
    base_fatigue_factor = getattr(labor_scheme, 'base_fatigue_factor', 0.1) if labor_scheme else 0.1
    recovery_rate = getattr(labor_scheme, 'recovery_rate', 0.3) if labor_scheme else 0.3
    workload_intensity = getattr(labor_scheme, 'workload_intensity', '中等') if labor_scheme else '中等'

    base_flow = calculate_base_flow_rate(well_config, worker_count, work_mode)
    fatigue_rate_per_min = calculate_fatigue_rate(
        worker_count, work_mode, base_fatigue_factor, workload_intensity, env_factor
    )

    time_points = []
    total_water = 0.0
    current_fatigue = 0.0
    peak_flow = 0.0
    total_work_min = 0.0
    total_rest_min = 0.0
    flows = []
    fatigue_values = []

    num_steps = int(simulation_duration_min / time_step_min) + 1

    cycle_total = continuous_duration_min + rest_duration_min if rest_interval_min > 0 else continuous_duration_min

    for step in range(num_steps):
        elapsed = step * time_step_min
        is_rest = False

        if rest_interval_min > 0 and continuous_duration_min > 0:
            cycle_pos = elapsed % cycle_total
            if cycle_pos >= continuous_duration_min:
                is_rest = True

        if shift_rotation and work_mode in ["双人轮流", "三人交替"] and not is_rest:
            shift_cycle = shift_duration_min * (worker_count if worker_count > 1 else 1)
            shift_pos = elapsed % shift_cycle
            current_worker = int(shift_pos / shift_duration_min) % worker_count
            active_workers = 1
        else:
            if work_mode in ["双人轮流", "三人交替"]:
                active_workers = 0 if is_rest else 1
            elif work_mode == "多人协同":
                active_workers = 0 if is_rest else min(worker_count, 3)
            else:
                active_workers = 0 if is_rest else worker_count

        if is_rest:
            fatigue_decay = recovery_rate / 60.0 * time_step_min * 3.0
            current_fatigue = max(0.0, current_fatigue - fatigue_decay)
            instant_flow = 0.0
            total_rest_min += time_step_min
        else:
            fatigue_gain = fatigue_rate_per_min * time_step_min * (1 + current_fatigue * 0.5)
            current_fatigue = min(1.0, current_fatigue + fatigue_gain)
            total_work_min += time_step_min

            fatigue_efficiency = 1.0 - current_fatigue * 0.6
            efficiency = env_factor * fatigue_efficiency

            if work_mode == "多人协同" and worker_count >= 2:
                synergy_bonus = 1.0 + (worker_count - 1) * 0.05
                efficiency *= synergy_bonus

            instant_flow = base_flow * efficiency
            total_water += instant_flow * time_step_min
            instant_flow = round(instant_flow, 4)

            if instant_flow > peak_flow:
                peak_flow = instant_flow

            flows.append(instant_flow)

        fatigue_values.append(current_fatigue)

        time_points.append({
            "point_index": step,
            "elapsed_min": round(elapsed, 2),
            "total_water_l": round(total_water, 2),
            "instantaneous_flow_lpm": instant_flow,
            "avg_fatigue_level": round(current_fatigue, 4),
            "active_worker_count": active_workers,
            "is_rest_period": is_rest,
            "efficiency_factor": round(env_factor * (1.0 - current_fatigue * 0.6), 4)
        })

    avg_flow = round(total_water / total_work_min, 2) if total_work_min > 0 else 0.0
    per_capita_flow = round(avg_flow / worker_count, 2) if worker_count > 0 else 0.0

    valid_flows = [f for f in flows if f > 0]
    if len(valid_flows) >= 3:
        first_half = valid_flows[: len(valid_flows) // 2]
        second_half = valid_flows[len(valid_flows) // 2:]
        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0
        efficiency_decay_pct = round(((avg_first - avg_second) / avg_first * 100) if avg_first > 0 else 0, 2)

        mean_flow = sum(valid_flows) / len(valid_flows)
        variance = sum((f - mean_flow) ** 2 for f in valid_flows) / len(valid_flows)
        std_flow = math.sqrt(variance) if variance > 0 else 0
        stability_cv = round((std_flow / mean_flow * 100) if mean_flow > 0 else 0, 2)
    else:
        efficiency_decay_pct = 0.0
        stability_cv = 0.0

    final_fatigue = round(current_fatigue, 4)
    avg_fatigue = round(sum(fatigue_values) / len(fatigue_values), 4) if fatigue_values else 0.0

    work_rest_ratio = round(total_work_min / total_rest_min, 2) if total_rest_min > 0 else 99.9

    overall_score = calculate_overall_score(
        avg_flow, per_capita_flow, efficiency_decay_pct,
        stability_cv, final_fatigue, work_rest_ratio
    )

    return {
        "env_factor": env_factor,
        "base_flow_lpm": base_flow,
        "peak_flow_lpm": round(peak_flow, 2),
        "avg_flow_lpm": avg_flow,
        "per_capita_flow_lpm": per_capita_flow,
        "total_water_l": round(total_water, 2),
        "total_work_min": round(total_work_min, 2),
        "total_rest_min": round(total_rest_min, 2),
        "work_rest_ratio": work_rest_ratio,
        "efficiency_decay_pct": efficiency_decay_pct,
        "final_fatigue_level": final_fatigue,
        "avg_fatigue_level": avg_fatigue,
        "stability_cv": stability_cv,
        "overall_score": overall_score,
        "time_points": time_points
    }


def calculate_overall_score(
    avg_flow: float,
    per_capita_flow: float,
    decay_pct: float,
    stability_cv: float,
    final_fatigue: float,
    work_rest_ratio: float
) -> float:
    score_flow = min(1.0, avg_flow / 30.0) * 0.25
    score_per_capita = min(1.0, per_capita_flow / 18.0) * 0.25
    score_decay = max(0.0, 1.0 - decay_pct / 50.0) * 0.2
    score_stability = max(0.0, 1.0 - stability_cv / 50.0) * 0.15
    score_fatigue = max(0.0, 1.0 - final_fatigue) * 0.1
    score_rest = 0.05 if work_rest_ratio < 20 else 0.0

    total = score_flow + score_per_capita + score_decay + score_stability + score_fatigue + score_rest
    return round(total * 100, 2)


def generate_optimization_recommendation(scene_config, labor_scheme, simulation_result: dict) -> dict:
    recommendations = []
    best_worker_count = simulation_result.get("per_capita_flow_lpm", 0)
    worker_count = getattr(labor_scheme, 'worker_count', 1) if labor_scheme else 1
    work_mode = getattr(labor_scheme, 'work_mode', '单人独立') if labor_scheme else '单人独立'
    rest_interval = getattr(labor_scheme, 'rest_interval_min', 0) if labor_scheme else 0
    continuous_duration = getattr(labor_scheme, 'continuous_duration_min', 30) if labor_scheme else 30

    decay_pct = simulation_result.get("efficiency_decay_pct", 0)
    final_fatigue = simulation_result.get("final_fatigue_level", 0)
    avg_flow = simulation_result.get("avg_flow_lpm", 0)
    per_capita = simulation_result.get("per_capita_flow_lpm", 0)

    if decay_pct > 25:
        recommendations.append({
            "aspect": "疲劳控制",
            "level": "high",
            "suggestion": f"效率衰减达{decay_pct:.1f}%，建议缩短单次连续作业时长或增加休息频率"
        })

    if final_fatigue > 0.7:
        recommendations.append({
            "aspect": "体力恢复",
            "level": "high",
            "suggestion": f"结束时疲劳度达{final_fatigue*100:.0f}%，建议采用轮班制或延长休息时间"
        })

    if rest_interval == 0 and decay_pct > 15:
        rest_advice = max(5, int(continuous_duration * 0.15))
        recommendations.append({
            "aspect": "休息节奏",
            "level": "medium",
            "suggestion": f"建议每{int(continuous_duration * 0.6)}分钟安排{rest_advice}分钟休息，可显著减缓效率下降"
        })

    if worker_count == 1 and decay_pct > 20:
        recommendations.append({
            "aspect": "人员配置",
            "level": "medium",
            "suggestion": "单人作业衰减明显，建议采用双人轮流模式提升持续作业能力"
        })

    if work_mode == "多人协同" and worker_count > 3:
        recommendations.append({
            "aspect": "协同效率",
            "level": "low",
            "suggestion": f"{worker_count}人协同的边际效益递减，建议优化分工或减少人数至2-3人"
        })

    scene = getattr(scene_config, 'config_name', '未知场景') if scene_config else '默认场景'
    scheme = getattr(labor_scheme, 'scheme_name', '未知方案') if labor_scheme else '默认方案'

    conclusion_parts = []
    conclusion_parts.append(f"在【{scene}】场景下，采用【{scheme}】：")
    conclusion_parts.append(f"平均出水量 {avg_flow:.2f} L/min，人均 {per_capita:.2f} L/min/人")
    conclusion_parts.append(f"效率衰减 {decay_pct:.1f}%，结束疲劳度 {final_fatigue*100:.0f}%")

    overall = simulation_result.get("overall_score", 0)
    if overall >= 80:
        conclusion_parts.append("综合评估：优秀方案，各方面表现均衡")
    elif overall >= 60:
        conclusion_parts.append("综合评估：良好方案，部分参数可进一步优化")
    elif overall >= 40:
        conclusion_parts.append("综合评估：一般方案，建议参考优化建议调整")
    else:
        conclusion_parts.append("综合评估：待改进方案，需重点优化休息节奏和人员配置")

    return {
        "recommendations": recommendations,
        "conclusion": "；".join(conclusion_parts),
        "best_worker_count": worker_count,
        "best_work_mode": work_mode,
        "suggested_rest_rhythm": f"每{int(continuous_duration)}分钟休息{int(getattr(labor_scheme, 'rest_duration_min', 5) if labor_scheme else 5)}分钟" if rest_interval > 0 else "连续作业"
    }


def compare_simulations(simulation_results: List[dict]) -> dict:
    if not simulation_results:
        return {"error": "没有可对比的模拟结果"}

    best_overall = max(simulation_results, key=lambda s: s.get("overall_score", 0))
    best_per_capita = max(simulation_results, key=lambda s: s.get("per_capita_flow_lpm", 0))
    best_sustained = max(simulation_results, key=lambda s: 100 - s.get("efficiency_decay_pct", 100))
    best_total = max(simulation_results, key=lambda s: s.get("total_water_l", 0))

    ranked = sorted(simulation_results, key=lambda s: s.get("overall_score", 0), reverse=True)
    for i, sim in enumerate(ranked):
        sim["ranking"] = i + 1

    return {
        "total_count": len(simulation_results),
        "best_overall": best_overall.get("simulation_name", ""),
        "best_overall_score": best_overall.get("overall_score", 0),
        "best_per_capita": best_per_capita.get("simulation_name", ""),
        "best_per_capita_value": best_per_capita.get("per_capita_flow_lpm", 0),
        "best_sustained": best_sustained.get("simulation_name", ""),
        "best_sustained_decay": best_sustained.get("efficiency_decay_pct", 0),
        "best_total": best_total.get("simulation_name", ""),
        "best_total_water": best_total.get("total_water_l", 0),
        "ranked_simulations": ranked
    }


def generate_scene_report_content(well, scene_configs, labor_schemes, simulation_results, report_data) -> str:
    lines = []
    lines.append(f"# {well.name} - 劳作组织优化与历史场景复原报告")
    lines.append("")
    lines.append("## 一、研究背景")
    lines.append("本报告针对古井汲水劳作的组织方式进行系统化模拟研究，通过设定不同的环境场景和劳作方案，")
    lines.append("分析各类条件下的汲水效率、疲劳衰减和持续作业表现，为历史场景复原和现代应用提供科学依据。")
    lines.append("")

    lines.append("## 二、研究对象")
    lines.append(f"- **古井名称**: {well.name}")
    if well.location:
        lines.append(f"- **地理位置**: {well.location}")
    if well.dynasty:
        lines.append(f"- **历史年代**: {well.dynasty}")
    if well.description:
        lines.append(f"- **简要描述**: {well.description}")
    lines.append("")

    lines.append("## 三、场景配置")
    lines.append(f"本次研究共设置 {len(scene_configs)} 种典型场景：")
    for i, scene in enumerate(scene_configs, 1):
        lines.append(f"### 场景{i}：{scene.config_name}")
        lines.append(f"- **季节**: {scene.season}")
        lines.append(f"- **时段**: {scene.time_of_day}")
        lines.append(f"- **气温**: {scene.temperature_c}°C")
        lines.append(f"- **湿度**: {scene.humidity_pct}%")
        lines.append(f"- **风力**: {scene.wind_level}级")
        lines.append(f"- **地面**: {scene.ground_condition}")
        if scene.water_level_m > 0:
            lines.append(f"- **水位变化**: +{scene.water_level_m}m")
        if scene.description:
            lines.append(f"- **说明**: {scene.description}")
        lines.append("")

    lines.append("## 四、劳作方案")
    lines.append(f"本次研究共对比 {len(labor_schemes)} 种劳作组织方式：")
    for i, scheme in enumerate(labor_schemes, 1):
        lines.append(f"### 方案{i}：{scheme.scheme_name}")
        lines.append(f"- **参与人数**: {scheme.worker_count}人")
        lines.append(f"- **分工方式**: {scheme.work_mode}")
        lines.append(f"- **连续作业**: {scheme.continuous_duration_min}分钟")
        if scheme.rest_interval_min > 0:
            lines.append(f"- **休息安排**: 每{scheme.rest_interval_min}分钟休息{scheme.rest_duration_min}分钟")
        else:
            lines.append("- **休息安排**: 无休息（连续作业）")
        if scheme.shift_rotation:
            lines.append(f"- **轮班制度**: 是（每班{scheme.shift_duration_min}分钟）")
        else:
            lines.append("- **轮班制度**: 否")
        lines.append(f"- **基础衰减系数**: {scheme.base_fatigue_factor}")
        lines.append(f"- **劳动强度**: {scheme.workload_intensity}")
        if scheme.description:
            lines.append(f"- **说明**: {scheme.description}")
        lines.append("")

    lines.append("## 五、模拟结果汇总")
    lines.append("")
    lines.append("| 场景 | 方案 | 平均出水量(L/min) | 人均出水量(L/min/人) | 效率衰减(%) | 结束疲劳度 | 综合评分 |")
    lines.append("|------|------|---------------------|-----------------------|-------------|------------|----------|")

    for sim in simulation_results:
        scene_name = sim.get("scene_name", "-")
        scheme_name = sim.get("scheme_name", "-")
        avg_flow = sim.get("avg_flow_lpm", 0)
        per_capita = sim.get("per_capita_flow_lpm", 0)
        decay = sim.get("efficiency_decay_pct", 0)
        fatigue = sim.get("final_fatigue_level", 0)
        score = sim.get("overall_score", 0)
        lines.append(f"| {scene_name} | {scheme_name} | {avg_flow:.2f} | {per_capita:.2f} | {decay:.1f} | {fatigue*100:.0f}% | {score:.1f} |")
    lines.append("")

    lines.append("## 六、最优方案推荐")
    if report_data.get("best_scheme_name"):
        lines.append(f"### 🏆 综合最优方案：{report_data.get('best_scheme_name', '')}")
        lines.append("")
    if report_data.get("optimal_worker_count"):
        lines.append(f"- **最优人数配置**: {report_data.get('optimal_worker_count')}人")
    if report_data.get("optimal_work_mode"):
        lines.append(f"- **最佳分工方式**: {report_data.get('optimal_work_mode')}")
    if report_data.get("suggested_rest_rhythm"):
        lines.append(f"- **推荐休息节奏**: {report_data.get('suggested_rest_rhythm')}")
    lines.append("")

    if report_data.get("recommendation"):
        lines.append("### 💡 优化建议")
        lines.append(report_data.get("recommendation", ""))
        lines.append("")

    lines.append("## 七、结论")
    if report_data.get("conclusions"):
        lines.append(report_data.get("conclusions", ""))
    else:
        lines.append("通过多场景、多方案的对比模拟分析，本研究系统揭示了古井汲水劳作的效率规律。")
        lines.append("研究表明，合理的人员配置和休息安排可显著提升持续作业效率，不同环境场景下的最优方案存在差异。")
        lines.append("建议根据实际季节、时段和地面条件灵活调整劳作组织方式，以达到最佳的人力利用效果。")
    lines.append("")

    lines.append("---")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append(f"*模拟场景数: {len(scene_configs)} | 劳作方案数: {len(labor_schemes)} | 模拟总次数: {len(simulation_results)}*")

    return "\n".join(lines)


def calculate_hydro_season_efficiency_curve(data_points: list) -> list:
    if len(data_points) < 2:
        return []
    curve = []
    for dp in data_points:
        curve.append({
            "elapsed_min": dp.elapsed_min,
            "flow_rate_lpm": dp.flow_rate_lpm,
            "draw_efficiency_pct": dp.draw_efficiency_pct,
        })
    return curve


def calculate_hydro_water_level_trend(data_points: list) -> list:
    if len(data_points) < 2:
        return []
    trend = []
    for dp in data_points:
        trend.append({
            "elapsed_min": dp.elapsed_min,
            "water_level_m": dp.water_level_m,
            "water_temp_c": dp.water_temp_c,
        })
    return trend


def calculate_hydro_env_sensitivity_coefficient(data_points: list) -> float:
    if len(data_points) < 3:
        return 0.0
    flows = [dp.flow_rate_lpm for dp in data_points]
    levels = [dp.water_level_m for dp in data_points]
    temps = [dp.water_temp_c for dp in data_points]
    valid_pairs = [(f, l, t) for f, l, t in zip(flows, levels, temps) if f > 0]
    if len(valid_pairs) < 3:
        return 0.0
    n = len(valid_pairs)
    f_vals = [p[0] for p in valid_pairs]
    mean_f = sum(f_vals) / n
    if mean_f <= 0:
        return 0.0
    variance = sum((f - mean_f) ** 2 for f in f_vals) / n
    std_f = math.sqrt(variance) if variance > 0 else 0
    cv = std_f / mean_f
    l_vals = [p[1] for p in valid_pairs]
    t_vals = [p[2] for p in valid_pairs]
    level_range = max(l_vals) - min(l_vals) if l_vals else 0
    temp_range = max(t_vals) - min(t_vals) if t_vals else 0
    env_variability = 0.0
    if level_range > 0:
        l_var = sum((l - sum(l_vals) / n) ** 2 for l in l_vals) / n
        l_std = math.sqrt(l_var) if l_var > 0 else 0
        l_cv = l_std / (sum(l_vals) / n) if sum(l_vals) > 0 else 0
        env_variability += l_cv
    if temp_range > 0:
        t_var = sum((t - sum(t_vals) / n) ** 2 for t in t_vals) / n
        t_std = math.sqrt(t_var) if t_var > 0 else 0
        t_cv = t_std / (sum(t_vals) / n) if sum(t_vals) > 0 else 0
        env_variability += t_cv
    if env_variability <= 0:
        return 0.0
    sensitivity = cv / env_variability
    return round(min(2.0, max(0.0, sensitivity)), 4)


def calculate_hydro_efficiency_periods(data_points: list) -> tuple:
    high_periods = []
    low_periods = []
    if len(data_points) < 2:
        return high_periods, low_periods
    
    efficiencies = []
    for dp in data_points:
        if hasattr(dp, 'draw_efficiency_pct') and dp.draw_efficiency_pct is not None:
            efficiencies.append(dp.draw_efficiency_pct)
        elif hasattr(dp, 'flow_rate_lpm') and dp.flow_rate_lpm is not None:
            efficiencies.append(dp.flow_rate_lpm)
        else:
            efficiencies.append(0)
    
    valid_effs = [e for e in efficiencies if e > 0]
    if not valid_effs:
        return high_periods, low_periods
    
    mean_eff = sum(valid_effs) / len(valid_effs)
    
    if all(hasattr(dp, 'draw_efficiency_pct') and dp.draw_efficiency_pct is not None for dp in data_points):
        high_threshold = 70.0
        low_threshold = 40.0
        use_percent = True
    else:
        high_threshold = mean_eff * 1.15
        low_threshold = mean_eff * 0.85
        use_percent = False
    
    i = 0
    n = len(data_points)
    
    while i < n:
        if efficiencies[i] >= high_threshold and efficiencies[i] > 0:
            start_idx = i
            sum_eff = 0
            count = 0
            while i < n and efficiencies[i] >= high_threshold and efficiencies[i] > 0:
                sum_eff += efficiencies[i]
                count += 1
                i += 1
            end_idx = i - 1
            avg_eff = sum_eff / count if count > 0 else 0
            high_periods.append({
                "start_min": round(data_points[start_idx].elapsed_min, 2),
                "end_min": round(data_points[end_idx].elapsed_min, 2),
                "duration_min": round(data_points[end_idx].elapsed_min - data_points[start_idx].elapsed_min, 2),
                "avg_efficiency": round(avg_eff, 2),
                "data_points": count,
                "is_percent": use_percent
            })
        elif efficiencies[i] <= low_threshold and efficiencies[i] > 0:
            start_idx = i
            sum_eff = 0
            count = 0
            while i < n and efficiencies[i] <= low_threshold and efficiencies[i] > 0:
                sum_eff += efficiencies[i]
                count += 1
                i += 1
            end_idx = i - 1
            avg_eff = sum_eff / count if count > 0 else 0
            low_periods.append({
                "start_min": round(data_points[start_idx].elapsed_min, 2),
                "end_min": round(data_points[end_idx].elapsed_min, 2),
                "duration_min": round(data_points[end_idx].elapsed_min - data_points[start_idx].elapsed_min, 2),
                "avg_efficiency": round(avg_eff, 2),
                "data_points": count,
                "is_percent": use_percent
            })
        else:
            i += 1
    
    return high_periods, low_periods


def calculate_hydro_correlation(x_vals: list, y_vals: list) -> float:
    paired = [(x, y) for x, y in zip(x_vals, y_vals) if x is not None and y is not None]
    if len(paired) < 3:
        return 0.0
    n = len(paired)
    xs = [p[0] for p in paired]
    ys = [p[1] for p in paired]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    numerator = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return round(numerator / (denom_x * denom_y), 4)


def detect_hydro_anomalies(data_points: list) -> list:
    warnings = []
    if len(data_points) < 3:
        return warnings
    flows = [dp.flow_rate_lpm for dp in data_points]
    valid_flows = [f for f in flows if f > 0]
    if len(valid_flows) < 3:
        return warnings
    mean_flow = sum(valid_flows) / len(valid_flows)
    variance = sum((f - mean_flow) ** 2 for f in valid_flows) / len(valid_flows)
    std_flow = math.sqrt(variance) if variance > 0 else 0.001
    for i, dp in enumerate(data_points):
        if dp.flow_rate_lpm <= 0:
            continue
        z_score = abs(dp.flow_rate_lpm - mean_flow) / std_flow if std_flow > 0 else 0
        if z_score > 2.0:
            warning_type = "flow_spike" if dp.flow_rate_lpm > mean_flow else "flow_drop"
            warnings.append({
                "point_index": i,
                "elapsed_min": dp.elapsed_min,
                "flow_rate_lpm": dp.flow_rate_lpm,
                "type": warning_type,
                "z_score": round(z_score, 2),
                "description": f"在{dp.elapsed_min}min处出水量{'偏高' if dp.flow_rate_lpm > mean_flow else '偏低'}，偏离均值{round(z_score, 1)}倍标准差"
            })
    levels = [dp.water_level_m for dp in data_points]
    for i in range(1, len(levels)):
        if levels[i] > 0 and levels[i - 1] > 0:
            change = (levels[i] - levels[i - 1]) / levels[i - 1] * 100
            if abs(change) > 10:
                warnings.append({
                    "point_index": i,
                    "elapsed_min": data_points[i].elapsed_min,
                    "type": "water_level_shift",
                    "change_pct": round(change, 1),
                    "description": f"在{data_points[i].elapsed_min}min处地下水位{'上升' if change > 0 else '下降'}{abs(round(change, 1))}%"
                })
    return warnings


def calculate_hydro_analysis(experiment, data_points: list) -> dict:
    import json
    if len(data_points) < 2:
        return {}
    season_curve = calculate_hydro_season_efficiency_curve(data_points)
    water_level_trend = calculate_hydro_water_level_trend(data_points)
    env_sensitivity = calculate_hydro_env_sensitivity_coefficient(data_points)
    high_periods, low_periods = calculate_hydro_efficiency_periods(data_points)
    anomaly_warnings = detect_hydro_anomalies(data_points)
    flows = [dp.flow_rate_lpm for dp in data_points]
    valid_flows = [f for f in flows if f > 0]
    avg_flow = sum(valid_flows) / len(valid_flows) if valid_flows else 0
    peak_flow = max(valid_flows) if valid_flows else 0
    stabilities = [dp.stability_index for dp in data_points]
    avg_stability = sum(stabilities) / len(stabilities) if stabilities else 0
    burdens = [dp.labor_burden_score for dp in data_points]
    avg_burden = sum(burdens) / len(burdens) if burdens else 0
    levels = [dp.water_level_m for dp in data_points]
    level_change_pct = 0.0
    if len(levels) >= 2 and levels[0] > 0:
        level_change_pct = round((levels[-1] - levels[0]) / levels[0] * 100, 2)
    temps = [dp.water_temp_c for dp in data_points]
    temp_corr = calculate_hydro_correlation(temps, flows)
    level_corr = calculate_hydro_correlation(levels, flows)
    quality_map = {"清澈": 1.0, "微浊": 0.8, "浑浊": 0.5, "异味": 0.3, "干涸": 0.0}
    quality_val = quality_map.get(getattr(experiment, 'water_quality', '清澈'), 1.0)
    quality_correlations = [quality_val] * len(flows)
    quality_corr = calculate_hydro_correlation(quality_correlations, flows)
    score_flow = min(1.0, avg_flow / 20.0) * 0.25
    score_stability = min(1.0, avg_stability) * 0.2
    score_sensitivity = max(0.0, 1.0 - env_sensitivity) * 0.15
    score_burden = max(0.0, 1.0 - avg_burden / 10.0) * 0.15
    score_quality = quality_val * 0.15
    score_level = max(0.0, 1.0 - abs(level_change_pct) / 50.0) * 0.1
    overall_score = round(score_flow + score_stability + score_sensitivity + score_burden + score_quality + score_level, 4)
    return {
        "season_efficiency_curve_json": json.dumps(season_curve, ensure_ascii=False),
        "water_level_trend_json": json.dumps(water_level_trend, ensure_ascii=False),
        "env_sensitivity_coefficient": env_sensitivity,
        "high_efficiency_periods_json": json.dumps(high_periods, ensure_ascii=False),
        "low_efficiency_periods_json": json.dumps(low_periods, ensure_ascii=False),
        "avg_flow_rate_lpm": round(avg_flow, 4),
        "peak_flow_rate_lpm": round(peak_flow, 4),
        "avg_stability_index": round(avg_stability, 4),
        "avg_labor_burden": round(avg_burden, 4),
        "water_level_change_pct": level_change_pct,
        "temp_efficiency_corr": temp_corr,
        "level_efficiency_corr": level_corr,
        "quality_efficiency_corr": quality_corr,
        "anomaly_warnings_json": json.dumps(anomaly_warnings, ensure_ascii=False),
        "overall_score": overall_score,
    }


def calculate_hydro_period_comparison(experiments_data: list) -> dict:
    import json
    if len(experiments_data) < 2:
        return {}
    sorted_by_season = sorted(experiments_data, key=lambda e: {"春季": 1, "夏季": 2, "秋季": 3, "冬季": 4}.get(e.get("season", "春季"), 1))
    season_comparison = []
    for exp in sorted_by_season:
        analysis = exp.get("analysis_result", {}) or {}
        season_comparison.append({
            "experiment_id": exp.get("id"),
            "experiment_name": exp.get("experiment_name", ""),
            "season": exp.get("season", ""),
            "weather": exp.get("weather", ""),
            "water_quality": exp.get("water_quality", ""),
            "avg_flow_rate_lpm": analysis.get("avg_flow_rate_lpm", 0),
            "peak_flow_rate_lpm": analysis.get("peak_flow_rate_lpm", 0),
            "avg_stability_index": analysis.get("avg_stability_index", 0),
            "avg_labor_burden": analysis.get("avg_labor_burden", 0),
            "env_sensitivity_coefficient": analysis.get("env_sensitivity_coefficient", 0),
            "overall_score": analysis.get("overall_score", 0),
        })
    best_overall = max(season_comparison, key=lambda x: x["overall_score"]) if season_comparison else None
    best_flow = max(season_comparison, key=lambda x: x["avg_flow_rate_lpm"]) if season_comparison else None
    best_stability = max(season_comparison, key=lambda x: x["avg_stability_index"]) if season_comparison else None
    recommendations = []
    if best_overall:
        recommendations.append(f"综合表现最优：{best_overall['season']}({best_overall['experiment_name']}), 评分{best_overall['overall_score']:.1f}")
    if best_flow:
        recommendations.append(f"平均出水量最高：{best_flow['season']}({best_flow['experiment_name']}), {best_flow['avg_flow_rate_lpm']:.2f}L/min")
    if best_stability:
        recommendations.append(f"出水稳定性最佳：{best_stability['season']}({best_stability['experiment_name']}), 稳定性指数{best_stability['avg_stability_index']:.3f}")
    return {
        "season_comparison": season_comparison,
        "best_overall": best_overall,
        "best_flow": best_flow,
        "best_stability": best_stability,
        "recommendations": recommendations,
    }


def generate_hydro_report_content(well, experiments, period_comparisons, report_data: dict) -> str:
    import json
    lines = []
    lines.append(f"# {well.name} - 水文环境与季节波动研究报告")
    lines.append("")
    lines.append("## 一、研究背景")
    lines.append("本报告针对古井在不同季节、天气、地下水位、井水温度、水质状态和取水频率条件下的汲水表现，")
    lines.append("系统分析环境变化对汲水效率、出水稳定性和人工负荷的影响，揭示水文环境与汲水效率的关联规律。")
    lines.append("")

    lines.append("## 二、研究对象")
    lines.append(f"- **古井名称**: {well.name}")
    if well.location:
        lines.append(f"- **地理位置**: {well.location}")
    if well.dynasty:
        lines.append(f"- **历史年代**: {well.dynasty}")
    lines.append(f"- **实验记录数**: {len(experiments)}")
    lines.append("")

    lines.append("## 三、实验环境条件汇总")
    lines.append("")
    lines.append("| 实验名称 | 季节 | 天气 | 水位(m) | 水温(°C) | 水质 | 取水频率 |")
    lines.append("|----------|------|------|---------|----------|------|----------|")
    for exp in experiments:
        lines.append(f"| {exp.experiment_name} | {exp.season} | {exp.weather} | {exp.underground_water_level_m} | {exp.well_water_temp_c} | {exp.water_quality} | {exp.draw_frequency}次/日 |")
    lines.append("")

    lines.append("## 四、关键分析指标")
    lines.append("")
    lines.append("| 实验名称 | 平均出水量(L/min) | 峰值出水量 | 稳定性指数 | 人工负荷 | 水位变化(%) | 环境敏感系数 | 综合评分 |")
    lines.append("|----------|-------------------|------------|------------|----------|-------------|-------------|----------|")
    for exp in experiments:
        a = exp.analysis_result
        if a:
            lines.append(f"| {exp.experiment_name} | {a.avg_flow_rate_lpm:.2f} | {a.peak_flow_rate_lpm:.2f} | {a.avg_stability_index:.3f} | {a.avg_labor_burden:.2f} | {a.water_level_change_pct:.1f} | {a.env_sensitivity_coefficient:.4f} | {a.overall_score:.1f} |")
    lines.append("")

    if period_comparisons:
        lines.append("## 五、多时间周期对比")
        for comp in period_comparisons:
            lines.append(f"### {comp.get('period_name', '未命名')}")
            sc = comp.get("season_comparison", [])
            if sc:
                for item in sc:
                    lines.append(f"- **{item['season']}** ({item['experiment_name']}): 平均出水量{item['avg_flow_rate_lpm']:.2f}L/min, 综合评分{item['overall_score']:.1f}")
            recs = comp.get("recommendations", [])
            if recs:
                lines.append("")
                lines.append("**对比结论：**")
                for rec in recs:
                    lines.append(f"- {rec}")
            lines.append("")

    if report_data.get("conclusions"):
        lines.append("## 六、结论")
        lines.append(report_data["conclusions"])
        lines.append("")

    lines.append("---")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append(f"*实验数: {len(experiments)} | 对比组数: {len(period_comparisons)}*")
    return "\n".join(lines)
