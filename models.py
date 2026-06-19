from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, CheckConstraint, UniqueConstraint
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

    configs = relationship("WellConfig", back_populates="well", cascade="all, delete-orphan")


class WellConfig(Base):
    __tablename__ = "well_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    well_id = Column(Integer, ForeignKey("well.id", ondelete="CASCADE"), nullable=False)
    well_depth_m = Column(Float, nullable=False)
    bucket_capacity_l = Column(Float, nullable=False)
    bucket_diameter_m = Column(Float, nullable=False)
    pulley_radius_m = Column(Float, nullable=False)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        CheckConstraint("well_depth_m > 0", name="ck_well_depth_positive"),
        CheckConstraint("bucket_capacity_l > 0", name="ck_bucket_capacity_positive"),
        CheckConstraint("bucket_diameter_m > 0", name="ck_bucket_diameter_positive"),
        CheckConstraint("pulley_radius_m > 0", name="ck_pulley_radius_positive"),
    )

    well = relationship("Well", back_populates="configs")
    experiments = relationship("Experiment", back_populates="config", cascade="all, delete-orphan")


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
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("config_id", "round_number", name="uq_config_round"),
    )

    config = relationship("WellConfig", back_populates="experiments")
    time_points = relationship("TimePoint", back_populates="experiment", cascade="all, delete-orphan", order_by="TimePoint.point_index")


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
