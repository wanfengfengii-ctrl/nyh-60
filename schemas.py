from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class WellBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = ""
    dynasty: Optional[str] = ""
    description: Optional[str] = ""


class WellCreate(WellBase):
    pass


class WellUpdate(WellBase):
    pass


class WellResponse(WellBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class WellConfigBase(BaseModel):
    well_depth_m: float = Field(..., gt=0, description="井深必须大于0米")
    bucket_capacity_l: float = Field(..., gt=0, description="桶容量必须大于0升")
    bucket_diameter_m: float = Field(..., gt=0, description="桶径必须大于0米")
    pulley_radius_m: float = Field(..., gt=0, description="绳轮半径必须大于0米")


class WellConfigCreate(WellConfigBase):
    pass


class WellConfigUpdate(WellConfigBase):
    pass


class WellConfigResponse(WellConfigBase):
    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class TimePointBase(BaseModel):
    point_index: int = Field(..., ge=0)
    time_s: float = Field(..., ge=0, description="时间点必须大于等于0秒")
    water_l: float = Field(..., ge=0, description="出水量必须大于等于0升")
    calculated_speed_rpm: Optional[float] = None


class TimePointCreate(TimePointBase):
    pass


class TimePointResponse(TimePointBase):
    id: int

    class Config:
        from_attributes = True


class ExperimentBase(BaseModel):
    round_number: int = Field(..., gt=0, description="轮次必须大于0")


class ExperimentCreate(ExperimentBase):
    time_points: List[TimePointCreate]

    @field_validator("time_points")
    @classmethod
    def validate_time_points(cls, v):
        if len(v) < 2:
            raise ValueError("至少需要2个时间点数据")
        times = [tp.time_s for tp in v]
        for i in range(1, len(times)):
            if times[i] <= times[i - 1]:
                raise ValueError(f"时间点必须严格递增：第{i}个时间点({times[i]})不大于第{i-1}个({times[i-1]})")
        return v


class ExperimentResponse(ExperimentBase):
    id: int
    config_id: int
    review_status: str
    total_time_s: Optional[float]
    total_water_l: Optional[float]
    flow_rate_lpm: Optional[float]
    avg_speed_rpm: Optional[float]
    is_abnormal: bool
    created_at: datetime
    time_points: List[TimePointResponse]

    class Config:
        from_attributes = True


class EfficiencyData(BaseModel):
    experiment_id: int
    round_number: int
    total_time_s: float
    total_water_l: float
    flow_rate_lpm: float
    avg_speed_rpm: float
    is_abnormal: bool
    review_status: str
    speed_curve: List[dict]


class ComparisonData(BaseModel):
    config_id: int
    bucket_diameter_m: float
    pulley_radius_m: float
    well_depth_m: float
    avg_flow_rate_lpm: float
    avg_speed_rpm: float
    experiment_count: int
    experiments: List[EfficiencyData]
