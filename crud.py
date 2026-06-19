from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from models import Well, WellConfig, Experiment, TimePoint
from schemas import (
    WellCreate, WellUpdate,
    WellConfigCreate, WellConfigUpdate,
    ExperimentCreate
)
from calculator import (
    calculate_experiment_efficiency,
    detect_anomalies,
    mark_experiments_for_review
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


def get_all_configs(db: Session, well_id: int) -> List[WellConfig]:
    return db.query(WellConfig).filter(
        WellConfig.well_id == well_id
    ).order_by(desc(WellConfig.created_at)).all()


def create_config(db: Session, well_id: int, data: WellConfigCreate) -> WellConfig:
    old_active = get_active_config(db, well_id)
    if old_active:
        old_active.status = "archived"
        mark_experiments_for_review(old_active.experiments)

    config = WellConfig(well_id=well_id, **data.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


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
        review_status="valid"
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
