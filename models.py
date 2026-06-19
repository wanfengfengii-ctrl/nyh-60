from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, CheckConstraint, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from database import Base


class Well(Base):
    __tablename__ = "well"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    location = Column(String(200), default="")
    dynasty = Column(String(50), default="")
    description = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    configs = relationship("WellConfig", back_populates="well", cascade="all, delete-orphan")


class WellConfig(Base):
    __tablename__ = "well_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    well_id = Column(Integer, ForeignKey("well.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, default=1)
    well_depth_m = Column(Float, nullable=False)
    bucket_capacity_l = Column(Float, nullable=False)
    bucket_diameter_m = Column(Float, nullable=False)
    pulley_radius_m = Column(Float, nullable=False)
    status = Column(String(20), default="active")
    change_note = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        CheckConstraint("well_depth_m > 0", name="ck_well_depth_positive"),
        CheckConstraint("bucket_capacity_l > 0", name="ck_bucket_capacity_positive"),
        CheckConstraint("bucket_diameter_m > 0", name="ck_bucket_diameter_positive"),
        CheckConstraint("pulley_radius_m > 0", name="ck_pulley_radius_positive"),
    )

    well = relationship("Well", back_populates="configs")
    experiments = relationship("Experiment", back_populates="config", cascade="all, delete-orphan")
    change_logs = relationship("ConfigChangeLog", back_populates="config", cascade="all, delete-orphan")


class ConfigChangeLog(Base):
    __tablename__ = "config_change_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("well_config.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(50), nullable=False)
    old_value = Column(String(100))
    new_value = Column(String(100))
    change_reason = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.now)

    config = relationship("WellConfig", back_populates="change_logs")


class Experiment(Base):
    __tablename__ = "experiment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("well_config.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    review_status = Column(String(20), default="valid")
    total_time_s = Column(Float)
    total_water_l = Column(Float)
    flow_rate_lpm = Column(Float)
    avg_speed_rpm = Column(Float)
    is_abnormal = Column(Boolean, default=False)
    notes = Column(String(1000), default="")
    reviewer = Column(String(100), default="")
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("config_id", "round_number", name="uq_config_round"),
    )

    config = relationship("WellConfig", back_populates="experiments")
    time_points = relationship("TimePoint", back_populates="experiment", cascade="all, delete-orphan", order_by="TimePoint.point_index")
    reviews = relationship("ExperimentReview", back_populates="experiment", cascade="all, delete-orphan")


class ExperimentReview(Base):
    __tablename__ = "experiment_review"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, ForeignKey("experiment.id", ondelete="CASCADE"), nullable=False)
    review_action = Column(String(20), nullable=False)
    reviewer = Column(String(100), default="")
    comment = Column(String(1000), default="")
    old_flow_rate = Column(Float)
    new_flow_rate = Column(Float)
    created_at = Column(DateTime, default=datetime.now)

    experiment = relationship("Experiment", back_populates="reviews")


class TimePoint(Base):
    __tablename__ = "time_point"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, ForeignKey("experiment.id", ondelete="CASCADE"), nullable=False)
    point_index = Column(Integer, nullable=False)
    time_s = Column(Float, nullable=False)
    water_l = Column(Float, nullable=False)
    calculated_speed_rpm = Column(Float)

    __table_args__ = (
        CheckConstraint("time_s >= 0", name="ck_time_non_negative"),
        CheckConstraint("water_l >= 0", name="ck_water_non_negative"),
        UniqueConstraint("experiment_id", "point_index", name="uq_exp_point"),
    )

    experiment = relationship("Experiment", back_populates="time_points")


class ImportExportLog(Base):
    __tablename__ = "import_export_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    well_id = Column(Integer, ForeignKey("well.id", ondelete="CASCADE"))
    operation_type = Column(String(10), nullable=False)
    file_name = Column(String(255), nullable=False)
    record_count = Column(Integer, default=0)
    operator = Column(String(100), default="")
    status = Column(String(20), default="success")
    error_message = Column(String(1000), default="")
    created_at = Column(DateTime, default=datetime.now)


class ExperimentReport(Base):
    __tablename__ = "experiment_report"

    id = Column(Integer, primary_key=True, autoincrement=True)
    well_id = Column(Integer, ForeignKey("well.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("well_config.id", ondelete="CASCADE"))
    title = Column(String(200), nullable=False)
    author = Column(String(100), default="")
    summary = Column(Text, default="")
    conclusions = Column(Text, default="")
    report_content = Column(Text, default="")
    experiment_count = Column(Integer, default=0)
    avg_flow_rate_lpm = Column(Float, default=0)
    avg_speed_rpm = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.now)


class LaborExperiment(Base):
    __tablename__ = "labor_experiment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    well_id = Column(Integer, ForeignKey("well.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("well_config.id", ondelete="CASCADE"))
    experiment_name = Column(String(200), nullable=False)
    worker_count = Column(Integer, nullable=False)
    work_mode = Column(String(50), nullable=False)
    continuous_duration_min = Column(Float, nullable=False)
    rest_interval_min = Column(Float, default=0)
    fatigue_factor = Column(Float, default=0.0)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        CheckConstraint("worker_count >= 1", name="ck_worker_count_positive"),
        CheckConstraint("continuous_duration_min > 0", name="ck_continuous_duration_positive"),
        CheckConstraint("rest_interval_min >= 0", name="ck_rest_interval_non_negative"),
        CheckConstraint("fatigue_factor >= 0 AND fatigue_factor <= 1", name="ck_fatigue_factor_range"),
    )

    well = relationship("Well")
    config = relationship("WellConfig")
    time_points = relationship("LaborTimePoint", back_populates="experiment", cascade="all, delete-orphan", order_by="LaborTimePoint.point_index")
    analysis_result = relationship("LaborAnalysisResult", back_populates="experiment", cascade="all, delete-orphan", uselist=False)


class LaborTimePoint(Base):
    __tablename__ = "labor_time_point"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, ForeignKey("labor_experiment.id", ondelete="CASCADE"), nullable=False)
    point_index = Column(Integer, nullable=False)
    elapsed_min = Column(Float, nullable=False)
    total_water_l = Column(Float, nullable=False)
    worker_rotation = Column(Integer, default=0)
    fatigue_level = Column(Float, default=0)
    is_rest_period = Column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint("elapsed_min >= 0", name="ck_elapsed_non_negative"),
        CheckConstraint("total_water_l >= 0", name="ck_total_water_non_negative"),
        CheckConstraint("fatigue_level >= 0 AND fatigue_level <= 1", name="ck_fatigue_level_range"),
        UniqueConstraint("experiment_id", "point_index", name="uq_labor_exp_point"),
    )

    experiment = relationship("LaborExperiment", back_populates="time_points")


class LaborAnalysisResult(Base):
    __tablename__ = "labor_analysis_result"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, ForeignKey("labor_experiment.id", ondelete="CASCADE"), nullable=False, unique=True)
    total_water_l = Column(Float, default=0)
    total_effective_min = Column(Float, default=0)
    total_rest_min = Column(Float, default=0)
    avg_flow_rate_lpm = Column(Float, default=0)
    per_capita_flow_lpm = Column(Float, default=0)
    peak_flow_rate_lpm = Column(Float, default=0)
    peak_duration_min = Column(Float, default=0)
    peak_start_min = Column(Float, default=0)
    efficiency_decay_pct = Column(Float, default=0)
    stability_cv = Column(Float, default=0)
    fatigue_correlation = Column(Float, default=0)
    work_rest_ratio = Column(Float, default=0)
    anomaly_flags = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)

    experiment = relationship("LaborExperiment", back_populates="analysis_result")


class LaborComparisonGroup(Base):
    __tablename__ = "labor_comparison_group"

    id = Column(Integer, primary_key=True, autoincrement=True)
    well_id = Column(Integer, ForeignKey("well.id", ondelete="CASCADE"), nullable=False)
    group_name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)

    well = relationship("Well")
    items = relationship("LaborComparisonItem", back_populates="group", cascade="all, delete-orphan")


class LaborComparisonItem(Base):
    __tablename__ = "labor_comparison_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("labor_comparison_group.id", ondelete="CASCADE"), nullable=False)
    experiment_id = Column(Integer, ForeignKey("labor_experiment.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("group_id", "experiment_id", name="uq_group_experiment"),
    )

    group = relationship("LaborComparisonGroup", back_populates="items")
    experiment = relationship("LaborExperiment")
