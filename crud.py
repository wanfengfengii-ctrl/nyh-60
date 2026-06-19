from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from models import (
    Well, WellConfig, Experiment, TimePoint,
    ConfigChangeLog, ExperimentReview, ImportExportLog, ExperimentReport,
    LaborExperiment, LaborTimePoint, LaborAnalysisResult,
    LaborComparisonGroup, LaborComparisonItem
)
from schemas import (
    WellCreate, WellUpdate,
    WellConfigCreate, WellConfigUpdate,
    ExperimentCreate, ExperimentUpdate,
    ExperimentReviewCreate, TimePointUpdate,
    ExperimentReportCreate,
    LaborExperimentCreate, LaborExperimentUpdate,
    LaborComparisonGroupCreate
)
from calculator import (
    calculate_experiment_efficiency,
    detect_anomalies,
    mark_experiments_for_review,
    recalculate_experiment,
    predict_efficiency,
    calculate_labor_analysis,
    calculate_synergy_gain,
    calculate_multi_round_comparison
)


def get_wells(db: Session, skip: int = 0, limit: int = 100) -> List[Well]:
    return db.query(Well).order_by(desc(Well.created_at)).offset(skip).limit(limit).all()


def get_well(db: Session, well_id: int) -> Optional[Well]:
    return db.query(Well).filter(Well.id == well_id).first()


def create_well(db: Session, data: WellCreate) -> Well:
    well = Well(**data.model_dump())
    db.add(well)
    db.commit()
    db.refresh(well)
    return well


def update_well(db: Session, db_obj: Well, data: WellUpdate) -> Well:
    for field, value in data.model_dump().items():
        setattr(db_obj, field, value)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def delete_well(db: Session, well_id: int) -> bool:
    well = get_well(db, well_id)
    if well:
        db.delete(well)
        db.commit()
        return True
    return False


def get_active_config(db: Session, well_id: int) -> Optional[WellConfig]:
    return db.query(WellConfig).filter(
        WellConfig.well_id == well_id,
        WellConfig.status == "active"
    ).order_by(desc(WellConfig.created_at)).first()


def get_config(db: Session, config_id: int) -> Optional[WellConfig]:
    return db.query(WellConfig).filter(WellConfig.id == config_id).first()


def get_all_configs(db: Session, well_id: int) -> List[WellConfig]:
    return db.query(WellConfig).filter(
        WellConfig.well_id == well_id
    ).order_by(desc(WellConfig.created_at)).all()


def log_config_changes(
    db: Session,
    config: WellConfig,
    old_config: Optional[WellConfig],
    change_reason: str = ""
) -> None:
    if not old_config:
        fields = ["well_depth_m", "bucket_capacity_l", "bucket_diameter_m", "pulley_radius_m"]
        for field in fields:
            log = ConfigChangeLog(
                config_id=config.id,
                field_name=field,
                old_value=None,
                new_value=str(getattr(config, field)),
                change_reason=change_reason
            )
            db.add(log)
        return
    field_map = {
        "well_depth_m": "井深",
        "bucket_capacity_l": "桶容量",
        "bucket_diameter_m": "桶径",
        "pulley_radius_m": "绳轮半径"
    }
    for field, label in field_map.items():
        old_val = getattr(old_config, field)
        new_val = getattr(config, field)
        if old_val != new_val:
            log = ConfigChangeLog(
                config_id=config.id,
                field_name=label,
                old_value=str(old_val),
                new_value=str(new_val),
                change_reason=change_reason
            )
            db.add(log)


def create_config(db: Session, well_id: int, data: WellConfigCreate) -> WellConfig:
    old_active = get_active_config(db, well_id)
    all_configs = get_all_configs(db, well_id)
    new_version = len(all_configs) + 1

    if old_active:
        old_active.status = "archived"
        mark_experiments_for_review(old_active.experiments)

    config = WellConfig(
        well_id=well_id,
        version=new_version,
        well_depth_m=data.well_depth_m,
        bucket_capacity_l=data.bucket_capacity_l,
        bucket_diameter_m=data.bucket_diameter_m,
        pulley_radius_m=data.pulley_radius_m,
        change_note=data.change_note or ""
    )
    db.add(config)
    db.flush()

    log_config_changes(db, config, old_active, data.change_note or "")

    db.commit()
    db.refresh(config)
    return config


def activate_config(db: Session, config_id: int) -> Optional[WellConfig]:
    config = get_config(db, config_id)
    if not config:
        return None
    old_active = get_active_config(db, config.well_id)
    if old_active and old_active.id != config_id:
        old_active.status = "archived"
        old_experiments = get_experiments(db, old_active.id)
        for exp in old_experiments:
            if exp.review_status == "valid":
                exp.review_status = "pending_review"
    config.status = "active"
    db.commit()
    db.refresh(config)
    return config


def get_config_change_logs(db: Session, config_id: int) -> List[ConfigChangeLog]:
    return db.query(ConfigChangeLog).filter(
        ConfigChangeLog.config_id == config_id
    ).order_by(desc(ConfigChangeLog.created_at)).all()


def get_all_pending_reviews(db: Session) -> List[Experiment]:
    return db.query(Experiment).filter(
        Experiment.review_status == "pending_review"
    ).order_by(desc(Experiment.created_at)).all()


def get_pending_reviews_for_well(db: Session, well_id: int) -> List[Experiment]:
    return db.query(Experiment).join(WellConfig).filter(
        WellConfig.well_id == well_id,
        Experiment.review_status == "pending_review"
    ).order_by(desc(Experiment.created_at)).all()


def get_experiments(db: Session, config_id: int) -> List[Experiment]:
    return db.query(Experiment).filter(
        Experiment.config_id == config_id
    ).order_by(Experiment.round_number).all()


def get_experiment(db: Session, exp_id: int) -> Optional[Experiment]:
    return db.query(Experiment).filter(Experiment.id == exp_id).first()


def get_experiment_by_round(db: Session, config_id: int, round_number: int) -> Optional[Experiment]:
    return db.query(Experiment).filter(
        Experiment.config_id == config_id,
        Experiment.round_number == round_number
    ).first()


def create_experiment(db: Session, config: WellConfig, data: ExperimentCreate) -> Optional[Experiment]:
    existing = get_experiment_by_round(db, config.id, data.round_number)
    if existing:
        return None

    max_water = max(tp.water_l for tp in data.time_points)
    if max_water > config.bucket_capacity_l:
        raise ValueError(f"出水量({max_water}L)超过桶容量({config.bucket_capacity_l}L)")

    experiment = Experiment(
        config_id=config.id,
        round_number=data.round_number,
        review_status="valid",
        notes=data.notes or ""
    )
    db.add(experiment)
    db.flush()

    for tp_data in data.time_points:
        tp = TimePoint(
            experiment_id=experiment.id,
            **tp_data.model_dump()
        )
        db.add(tp)

    db.flush()

    total_time, total_water, flow_rate, avg_speed, speed_curve = calculate_experiment_efficiency(experiment, config)
    experiment.total_time_s = total_time
    experiment.total_water_l = total_water
    experiment.flow_rate_lpm = flow_rate
    experiment.avg_speed_rpm = avg_speed

    for i, tp in enumerate(experiment.time_points):
        if i < len(speed_curve):
            tp.calculated_speed_rpm = speed_curve[i]["rpm"]

    all_exps = get_experiments(db, config.id)
    detect_anomalies(all_exps)

    db.commit()
    db.refresh(experiment)
    return experiment


def update_experiment(
    db: Session,
    experiment: Experiment,
    data: ExperimentUpdate,
    config: WellConfig
) -> Experiment:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(experiment, field, value)

    recalculate_experiment(experiment, config)

    all_exps = get_experiments(db, config.id)
    detect_anomalies(all_exps)

    db.commit()
    db.refresh(experiment)
    return experiment


def update_experiment_time_points(
    db: Session,
    experiment: Experiment,
    time_points_data: List[Dict[str, Any]],
    config: WellConfig
) -> Experiment:
    max_water = max(tp["water_l"] for tp in time_points_data)
    if max_water > config.bucket_capacity_l:
        raise ValueError(f"出水量({max_water}L)超过桶容量({config.bucket_capacity_l}L)")

    times = [tp["time_s"] for tp in time_points_data]
    for i in range(1, len(times)):
        if times[i] <= times[i - 1]:
            raise ValueError(f"时间点必须严格递增：第{i+1}个时间点({times[i]})不大于第{i}个({times[i-1]})")

    for tp in experiment.time_points:
        db.delete(tp)
    db.flush()

    for idx, tp_data in enumerate(time_points_data):
        tp = TimePoint(
            experiment_id=experiment.id,
            point_index=tp_data.get("point_index", idx),
            time_s=tp_data["time_s"],
            water_l=tp_data["water_l"]
        )
        db.add(tp)

    db.flush()
    recalculate_experiment(experiment, config)

    all_exps = get_experiments(db, config.id)
    detect_anomalies(all_exps)

    db.commit()
    db.refresh(experiment)
    return experiment


def review_experiment(
    db: Session,
    experiment: Experiment,
    config: WellConfig,
    review_data: ExperimentReviewCreate
) -> Experiment:
    old_flow_rate = experiment.flow_rate_lpm
    new_flow_rate = old_flow_rate

    review = ExperimentReview(
        experiment_id=experiment.id,
        review_action=review_data.review_action,
        reviewer=review_data.reviewer or "",
        comment=review_data.comment or "",
        old_flow_rate=old_flow_rate
    )

    if review_data.review_action == "approve":
        experiment.review_status = "valid"
        experiment.reviewer = review_data.reviewer or ""
        experiment.reviewed_at = datetime.now()
    elif review_data.review_action == "reject":
        experiment.review_status = "rejected"
        experiment.reviewer = review_data.reviewer or ""
        experiment.reviewed_at = datetime.now()
    elif review_data.review_action == "recalculate":
        recalculate_experiment(experiment, config)
        experiment.review_status = "valid"
        experiment.reviewer = review_data.reviewer or ""
        experiment.reviewed_at = datetime.now()
        new_flow_rate = experiment.flow_rate_lpm

    review.new_flow_rate = new_flow_rate
    db.add(review)

    all_exps = get_experiments(db, config.id)
    detect_anomalies(all_exps)

    db.commit()
    db.refresh(experiment)
    return experiment


def recalculate_all_for_config(db: Session, config: WellConfig) -> int:
    experiments = get_experiments(db, config.id)
    for exp in experiments:
        recalculate_experiment(exp, config)
    detect_anomalies(experiments)
    db.commit()
    return len(experiments)


def delete_experiment(db: Session, exp_id: int, config: WellConfig) -> bool:
    exp = get_experiment(db, exp_id)
    if exp:
        db.delete(exp)
        db.flush()
        remaining = get_experiments(db, config.id)
        detect_anomalies(remaining)
        db.commit()
        return True
    return False


def get_experiment_reviews(db: Session, exp_id: int) -> List[ExperimentReview]:
    return db.query(ExperimentReview).filter(
        ExperimentReview.experiment_id == exp_id
    ).order_by(desc(ExperimentReview.created_at)).all()


def get_import_export_logs(db: Session, skip: int = 0, limit: int = 100) -> List[ImportExportLog]:
    return db.query(ImportExportLog).order_by(desc(ImportExportLog.created_at)).offset(skip).limit(limit).all()


def create_import_export_log(db: Session, data: Dict[str, Any]) -> ImportExportLog:
    log = ImportExportLog(**data)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_reports(db: Session, well_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[ExperimentReport]:
    query = db.query(ExperimentReport)
    if well_id:
        query = query.filter(ExperimentReport.well_id == well_id)
    return query.order_by(desc(ExperimentReport.created_at)).offset(skip).limit(limit).all()


def get_report(db: Session, report_id: int) -> Optional[ExperimentReport]:
    return db.query(ExperimentReport).filter(ExperimentReport.id == report_id).first()


def generate_report_content(
    well: Well,
    config: Optional[WellConfig],
    experiments: List[Experiment]
) -> str:
    valid_exps = [e for e in experiments if e.review_status == "valid"]
    lines = []
    lines.append(f"# {well.name} - 汲水效率研究报告")
    lines.append("")
    lines.append("## 古井基本信息")
    lines.append(f"- **井名**: {well.name}")
    if well.location:
        lines.append(f"- **位置**: {well.location}")
    if well.dynasty:
        lines.append(f"- **年代**: {well.dynasty}")
    if well.description:
        lines.append(f"- **描述**: {well.description}")
    lines.append("")

    if config:
        lines.append("## 辘轳结构参数")
        lines.append(f"- **版本**: v{config.version}")
        lines.append(f"- **井深**: {config.well_depth_m} m")
        lines.append(f"- **桶容量**: {config.bucket_capacity_l} L")
        lines.append(f"- **桶径**: {config.bucket_diameter_m} m")
        lines.append(f"- **绳轮半径**: {config.pulley_radius_m} m")
        if config.change_note:
            lines.append(f"- **变更说明**: {config.change_note}")
        lines.append("")

    lines.append("## 实验数据汇总")
    lines.append(f"- **实验总轮次**: {len(experiments)}")
    lines.append(f"- **有效轮次**: {len(valid_exps)}")
    lines.append(f"- **待复核轮次**: {len([e for e in experiments if e.review_status == 'pending_review'])}")
    lines.append(f"- **异常轮次**: {len([e for e in experiments if e.is_abnormal])}")

    if valid_exps:
        flow_rates = [e.flow_rate_lpm for e in valid_exps if e.flow_rate_lpm]
        speeds = [e.avg_speed_rpm for e in valid_exps if e.avg_speed_rpm]
        if flow_rates:
            lines.append(f"- **平均出水量**: {round(sum(flow_rates)/len(flow_rates), 2)} L/min")
            lines.append(f"- **最大出水量**: {round(max(flow_rates), 2)} L/min")
            lines.append(f"- **最小出水量**: {round(min(flow_rates), 2)} L/min")
        if speeds:
            lines.append(f"- **平均转速**: {round(sum(speeds)/len(speeds), 2)} rpm")
    lines.append("")

    lines.append("## 各轮实验详情")
    for exp in experiments:
        status_label = "有效" if exp.review_status == "valid" else ("待复核" if exp.review_status == "pending_review" else "已拒绝")
        lines.append(f"### 第{exp.round_number}轮实验")
        lines.append(f"- **状态**: {status_label}{' (异常偏低)' if exp.is_abnormal else ''}")
        lines.append(f"- **单次耗时**: {exp.total_time_s} s")
        lines.append(f"- **总出水量**: {exp.total_water_l} L")
        lines.append(f"- **单位出水量**: {exp.flow_rate_lpm} L/min")
        lines.append(f"- **平均转速**: {exp.avg_speed_rpm} rpm")
        if exp.notes:
            lines.append(f"- **备注**: {exp.notes}")
        lines.append("")

    lines.append("---")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    return "\n".join(lines)


def create_report(
    db: Session,
    well: Well,
    config: Optional[WellConfig],
    experiments: List[Experiment],
    data: ExperimentReportCreate
) -> ExperimentReport:
    valid_exps = [e for e in experiments if e.review_status == "valid"]
    flow_rates = [e.flow_rate_lpm for e in valid_exps if e.flow_rate_lpm]
    speeds = [e.avg_speed_rpm for e in valid_exps if e.avg_speed_rpm]
    avg_flow = round(sum(flow_rates) / len(flow_rates), 2) if flow_rates else 0.0
    avg_speed = round(sum(speeds) / len(speeds), 2) if speeds else 0.0

    report_content = generate_report_content(well, config, experiments)

    report = ExperimentReport(
        well_id=well.id,
        config_id=config.id if config else None,
        title=data.title,
        author=data.author or "",
        summary=data.summary or "",
        conclusions=data.conclusions or "",
        report_content=report_content,
        experiment_count=len(valid_exps),
        avg_flow_rate_lpm=avg_flow,
        avg_speed_rpm=avg_speed
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def delete_report(db: Session, report_id: int) -> bool:
    report = get_report(db, report_id)
    if report:
        db.delete(report)
        db.commit()
        return True
    return False


def predict_well_efficiency(
    db: Session,
    well_id: int,
    well_depth_m: float,
    bucket_capacity_l: float,
    bucket_diameter_m: float,
    pulley_radius_m: float,
    target_rpm: Optional[float] = None
) -> Dict[str, Any]:
    config = WellConfig(
        well_depth_m=well_depth_m,
        bucket_capacity_l=bucket_capacity_l,
        bucket_diameter_m=bucket_diameter_m,
        pulley_radius_m=pulley_radius_m
    )
    historical_rpms = []
    well = get_well(db, well_id)
    if well:
        for cfg in well.configs:
            for exp in cfg.experiments:
                if exp.review_status == "valid" and exp.avg_speed_rpm:
                    historical_rpms.append(exp.avg_speed_rpm)
    return predict_efficiency(config, target_rpm, historical_rpms)


def get_labor_experiments(
    db: Session, well_id: Optional[int] = None, skip: int = 0, limit: int = 100
) -> List[LaborExperiment]:
    query = db.query(LaborExperiment)
    if well_id:
        query = query.filter(LaborExperiment.well_id == well_id)
    return query.order_by(desc(LaborExperiment.created_at)).offset(skip).limit(limit).all()


def get_labor_experiment(db: Session, exp_id: int) -> Optional[LaborExperiment]:
    return db.query(LaborExperiment).filter(LaborExperiment.id == exp_id).first()


def create_labor_experiment(
    db: Session, data: LaborExperimentCreate, well_id: int
) -> LaborExperiment:
    if data.config_id:
        cfg = get_config(db, data.config_id)
        if not cfg or cfg.well_id != well_id:
            raise ValueError("指定的参数配置不存在或不属于该古井")

    experiment = LaborExperiment(
        well_id=well_id,
        config_id=data.config_id,
        experiment_name=data.experiment_name,
        worker_count=data.worker_count,
        work_mode=data.work_mode,
        continuous_duration_min=data.continuous_duration_min,
        rest_interval_min=data.rest_interval_min or 0,
        fatigue_factor=data.fatigue_factor or 0,
        notes=data.notes or "",
    )
    db.add(experiment)
    db.flush()

    for tp_data in data.time_points:
        tp = LaborTimePoint(
            experiment_id=experiment.id,
            point_index=tp_data.point_index,
            elapsed_min=tp_data.elapsed_min,
            total_water_l=tp_data.total_water_l,
            worker_rotation=tp_data.worker_rotation or 0,
            fatigue_level=tp_data.fatigue_level or 0,
            is_rest_period=tp_data.is_rest_period or False,
        )
        db.add(tp)

    db.flush()

    analysis_data = calculate_labor_analysis(experiment, experiment.time_points)
    existing_result = (
        db.query(LaborAnalysisResult)
        .filter(LaborAnalysisResult.experiment_id == experiment.id)
        .first()
    )
    if existing_result:
        db.delete(existing_result)
        db.flush()

    analysis_result = LaborAnalysisResult(
        experiment_id=experiment.id,
        total_water_l=analysis_data["total_water_l"],
        total_effective_min=analysis_data["total_effective_min"],
        total_rest_min=analysis_data["total_rest_min"],
        avg_flow_rate_lpm=analysis_data["avg_flow_rate_lpm"],
        per_capita_flow_lpm=analysis_data["per_capita_flow_lpm"],
        peak_flow_rate_lpm=analysis_data["peak_flow_rate_lpm"],
        peak_duration_min=analysis_data["peak_duration_min"],
        peak_start_min=analysis_data["peak_start_min"],
        efficiency_decay_pct=analysis_data["efficiency_decay_pct"],
        stability_cv=analysis_data["stability_cv"],
        fatigue_correlation=analysis_data["fatigue_correlation"],
        work_rest_ratio=analysis_data["work_rest_ratio"],
        anomaly_flags=analysis_data["anomaly_flags"],
    )
    db.add(analysis_result)

    db.commit()
    db.refresh(experiment)
    return experiment


def update_labor_experiment(
    db: Session, experiment: LaborExperiment, data: LaborExperimentUpdate
) -> LaborExperiment:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(experiment, field, value)

    db.flush()

    analysis_data = calculate_labor_analysis(experiment, experiment.time_points)
    existing_result = (
        db.query(LaborAnalysisResult)
        .filter(LaborAnalysisResult.experiment_id == experiment.id)
        .first()
    )
    if existing_result:
        for k, v in analysis_data.items():
            if hasattr(existing_result, k) and k != "anomaly_list" and k != "instantaneous_flows":
                setattr(existing_result, k, v)
    else:
        analysis_result = LaborAnalysisResult(
            experiment_id=experiment.id,
            total_water_l=analysis_data["total_water_l"],
            total_effective_min=analysis_data["total_effective_min"],
            total_rest_min=analysis_data["total_rest_min"],
            avg_flow_rate_lpm=analysis_data["avg_flow_rate_lpm"],
            per_capita_flow_lpm=analysis_data["per_capita_flow_lpm"],
            peak_flow_rate_lpm=analysis_data["peak_flow_rate_lpm"],
            peak_duration_min=analysis_data["peak_duration_min"],
            peak_start_min=analysis_data["peak_start_min"],
            efficiency_decay_pct=analysis_data["efficiency_decay_pct"],
            stability_cv=analysis_data["stability_cv"],
            fatigue_correlation=analysis_data["fatigue_correlation"],
            work_rest_ratio=analysis_data["work_rest_ratio"],
            anomaly_flags=analysis_data["anomaly_flags"],
        )
        db.add(analysis_result)

    db.commit()
    db.refresh(experiment)
    return experiment


def update_labor_time_points(
    db: Session, experiment: LaborExperiment, time_points_data: List[Dict[str, Any]]
) -> LaborExperiment:
    elapsed_list = [tp["elapsed_min"] for tp in time_points_data]
    for i in range(1, len(elapsed_list)):
        if elapsed_list[i] <= elapsed_list[i - 1]:
            raise ValueError(f"时间点必须严格递增：第{i+1}个({elapsed_list[i]}min)不大于第{i}个({elapsed_list[i-1]}min)")

    waters = [tp["total_water_l"] for tp in time_points_data]
    for i in range(1, len(waters)):
        if waters[i] < waters[i - 1]:
            raise ValueError(f"累计出水量不能减少：第{i+1}个({waters[i]}L)小于第{i}个({waters[i-1]}L)")

    for tp in experiment.time_points:
        db.delete(tp)
    db.flush()

    for idx, tp_data in enumerate(time_points_data):
        tp = LaborTimePoint(
            experiment_id=experiment.id,
            point_index=tp_data.get("point_index", idx),
            elapsed_min=tp_data["elapsed_min"],
            total_water_l=tp_data["total_water_l"],
            worker_rotation=tp_data.get("worker_rotation", 0),
            fatigue_level=tp_data.get("fatigue_level", 0),
            is_rest_period=tp_data.get("is_rest_period", False),
        )
        db.add(tp)

    db.flush()

    analysis_data = calculate_labor_analysis(experiment, experiment.time_points)
    existing_result = (
        db.query(LaborAnalysisResult)
        .filter(LaborAnalysisResult.experiment_id == experiment.id)
        .first()
    )
    if existing_result:
        for k, v in analysis_data.items():
            if hasattr(existing_result, k) and k != "anomaly_list" and k != "instantaneous_flows":
                setattr(existing_result, k, v)

    db.commit()
    db.refresh(experiment)
    return experiment


def delete_labor_experiment(db: Session, exp_id: int) -> bool:
    experiment = get_labor_experiment(db, exp_id)
    if experiment:
        db.delete(experiment)
        db.commit()
        return True
    return False


def recalculate_labor_experiment(db: Session, experiment: LaborExperiment) -> LaborAnalysisResult:
    analysis_data = calculate_labor_analysis(experiment, experiment.time_points)
    existing_result = (
        db.query(LaborAnalysisResult)
        .filter(LaborAnalysisResult.experiment_id == experiment.id)
        .first()
    )
    if existing_result:
        for k, v in analysis_data.items():
            if hasattr(existing_result, k) and k != "anomaly_list" and k != "instantaneous_flows":
                setattr(existing_result, k, v)
        db.commit()
        db.refresh(existing_result)
        return existing_result
    else:
        result = LaborAnalysisResult(
            experiment_id=experiment.id,
            total_water_l=analysis_data["total_water_l"],
            total_effective_min=analysis_data["total_effective_min"],
            total_rest_min=analysis_data["total_rest_min"],
            avg_flow_rate_lpm=analysis_data["avg_flow_rate_lpm"],
            per_capita_flow_lpm=analysis_data["per_capita_flow_lpm"],
            peak_flow_rate_lpm=analysis_data["peak_flow_rate_lpm"],
            peak_duration_min=analysis_data["peak_duration_min"],
            peak_start_min=analysis_data["peak_start_min"],
            efficiency_decay_pct=analysis_data["efficiency_decay_pct"],
            stability_cv=analysis_data["stability_cv"],
            fatigue_correlation=analysis_data["fatigue_correlation"],
            work_rest_ratio=analysis_data["work_rest_ratio"],
            anomaly_flags=analysis_data["anomaly_flags"],
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result


def get_labor_comparison_groups(
    db: Session, well_id: Optional[int] = None, skip: int = 0, limit: int = 50
) -> List[LaborComparisonGroup]:
    query = db.query(LaborComparisonGroup)
    if well_id:
        query = query.filter(LaborComparisonGroup.well_id == well_id)
    return query.order_by(desc(LaborComparisonGroup.created_at)).offset(skip).limit(limit).all()


def get_labor_comparison_group(db: Session, group_id: int) -> Optional[LaborComparisonGroup]:
    return db.query(LaborComparisonGroup).filter(LaborComparisonGroup.id == group_id).first()


def create_labor_comparison_group(
    db: Session, data: LaborComparisonGroupCreate
) -> LaborComparisonGroup:
    well = get_well(db, data.well_id)
    if not well:
        raise ValueError("指定的古井不存在")

    for item in data.items:
        exp = get_labor_experiment(db, item.experiment_id)
        if not exp or exp.well_id != data.well_id:
            raise ValueError(f"实验ID {item.experiment_id} 不存在或不属于该古井")

    group = LaborComparisonGroup(
        well_id=data.well_id,
        group_name=data.group_name,
        description=data.description or "",
    )
    db.add(group)
    db.flush()

    for item_data in data.items:
        item = LaborComparisonItem(
            group_id=group.id,
            experiment_id=item_data.experiment_id,
            sort_order=item_data.sort_order or 0,
        )
        db.add(item)

    db.commit()
    db.refresh(group)
    return group


def delete_labor_comparison_group(db: Session, group_id: int) -> bool:
    group = get_labor_comparison_group(db, group_id)
    if group:
        db.delete(group)
        db.commit()
        return True
    return False


def analyze_labor_comparison_group(db: Session, group: LaborComparisonGroup) -> Dict[str, Any]:
    from calculator import calculate_labor_instantaneous_flows, detect_labor_anomalies
    items = sorted(group.items, key=lambda x: x.sort_order)
    experiments = []
    for item in items:
        exp = get_labor_experiment(db, item.experiment_id)
        if exp:
            experiments.append(exp)

    if len(experiments) < 2:
        return {"error": "对比组至少需要2组有效实验数据"}

    items_response = []
    exp_dicts = []
    for exp in experiments:
        analysis = exp.analysis_result
        flows = calculate_labor_instantaneous_flows(exp.time_points)
        anomalies = detect_labor_anomalies(exp.time_points, flows)
        tps = []
        for i, tp in enumerate(exp.time_points):
            tps.append({
                "point_index": tp.point_index,
                "elapsed_min": tp.elapsed_min,
                "total_water_l": tp.total_water_l,
                "worker_rotation": tp.worker_rotation,
                "fatigue_level": tp.fatigue_level,
                "is_rest_period": tp.is_rest_period,
                "instantaneous_flow_lpm": flows[i] if i < len(flows) else 0
            })
        analysis_dict = {}
        if analysis:
            analysis_dict = {
                "total_water_l": analysis.total_water_l,
                "total_effective_min": analysis.total_effective_min,
                "total_rest_min": analysis.total_rest_min,
                "avg_flow_lpm": analysis.avg_flow_rate_lpm,
                "avg_flow_rate_lpm": analysis.avg_flow_rate_lpm,
                "per_capita_flow_lpm": analysis.per_capita_flow_lpm,
                "peak_flow_rate_lpm": analysis.peak_flow_rate_lpm,
                "peak_duration_min": analysis.peak_duration_min,
                "peak_start_min": analysis.peak_start_min,
                "peak_info": {
                    "peak_flow_lpm": analysis.peak_flow_rate_lpm,
                    "peak_start_min": analysis.peak_start_min,
                    "peak_end_min": (analysis.peak_start_min or 0) + (analysis.peak_duration_min or 0),
                    "duration_min": analysis.peak_duration_min,
                    "peak_time_min": analysis.peak_start_min
                },
                "efficiency_decay_pct": analysis.efficiency_decay_pct,
                "efficiency_decay_rate": (analysis.efficiency_decay_pct or 0) / 100.0,
                "stability_cv": analysis.stability_cv,
                "fatigue_correlation": analysis.fatigue_correlation,
                "work_rest_ratio": analysis.work_rest_ratio,
                "anomaly_flags": analysis.anomaly_flags,
                "anomalies": anomalies,
                "anomaly_list": anomalies,
                "overall_score": None
            }
        exp_dict = {
            "id": exp.id,
            "experiment_name": exp.experiment_name,
            "worker_count": exp.worker_count,
            "work_mode": exp.work_mode,
            "continuous_duration_min": exp.continuous_duration_min,
            "rest_interval_min": exp.rest_interval_min,
            "analysis_result": analysis_dict,
        }
        exp_dicts.append(exp_dict)
        items_response.append({
            "experiment": {
                "id": exp.id,
                "experiment_name": exp.experiment_name,
                "worker_count": exp.worker_count,
                "work_mode": exp.work_mode
            },
            "experiment_id": exp.id,
            "time_points": tps,
            "instantaneous_flows": [{"time_min": t.elapsed_min, "flow_lpm": flows[i] if i < len(flows) else 0} for i, t in enumerate(exp.time_points)],
            "analysis_result": analysis_dict
        })

    synergy_analysis = None
    synergy_gain = None
    single_exp = next((e for e in exp_dicts if e["worker_count"] == 1), None)
    multi_exps = [e for e in exp_dicts if e["worker_count"] > 1]
    if single_exp and multi_exps:
        best_multi = max(multi_exps, key=lambda e: e["analysis_result"].get("per_capita_flow_lpm", 0))
        synergy_analysis = calculate_synergy_gain(
            single_exp.get("analysis_result", {}),
            best_multi.get("analysis_result", {}),
        )
        synergy_analysis["baseline_experiment"] = single_exp["experiment_name"]
        synergy_analysis["compared_experiment"] = best_multi["experiment_name"]
        synergy_gain = synergy_analysis

    multi_round = calculate_multi_round_comparison(exp_dicts)
    recommendation = multi_round if multi_round and "best_scheme_name" in multi_round else None

    return {
        "success": True,
        "group_id": group.id,
        "group_name": group.group_name,
        "description": group.description,
        "experiments": exp_dicts,
        "items": items_response,
        "item_count": len(items_response),
        "synergy_analysis": synergy_analysis,
        "synergy_gain": synergy_gain,
        "multi_round_comparison": multi_round,
        "recommendation": recommendation,
    }
