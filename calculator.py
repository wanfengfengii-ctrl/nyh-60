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
