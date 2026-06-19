from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from models import (
    Well, WellConfig, Experiment, TimePoint,
    ConfigChangeLog, ExperimentReview, ImportExportLog, ExperimentReport
)
from schemas import (
    WellCreate, WellUpdate,
    WellConfigCreate, WellConfigUpdate,
    ExperimentCreate, ExperimentUpdate,
    ExperimentReviewCreate, TimePointUpdate,
    ExperimentReportCreate
)
from calculator import (
    calculate_experiment_efficiency,
    detect_anomalies,
    mark_experiments_for_review,
    recalculate_experiment,
    predict_efficiency
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
