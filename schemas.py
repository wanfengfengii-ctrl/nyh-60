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
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WellConfigBase(BaseModel):
    well_depth_m: float = Field(..., gt=0, description="井深必须大于0米")
    bucket_capacity_l: float = Field(..., gt=0, description="桶容量必须大于0升")
    bucket_diameter_m: float = Field(..., gt=0, description="桶径必须大于0米")
    pulley_radius_m: float = Field(..., gt=0, description="绳轮半径必须大于0米")
    change_note: Optional[str] = Field("", max_length=500)


class WellConfigCreate(WellConfigBase):
    pass


class WellConfigUpdate(WellConfigBase):
    pass


class WellConfigResponse(WellConfigBase):
    id: int
    well_id: int
    version: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConfigChangeLogResponse(BaseModel):
    id: int
    config_id: int
    field_name: str
    old_value: Optional[str]
    new_value: Optional[str]
    change_reason: str
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


class TimePointUpdate(BaseModel):
    point_index: Optional[int] = Field(None, ge=0)
    time_s: Optional[float] = Field(None, ge=0)
    water_l: Optional[float] = Field(None, ge=0)


class TimePointResponse(TimePointBase):
    id: int

    class Config:
        from_attributes = True


class ExperimentBase(BaseModel):
    round_number: int = Field(..., gt=0, description="轮次必须大于0")


class ExperimentCreate(ExperimentBase):
    time_points: List[TimePointCreate]
    notes: Optional[str] = Field("", max_length=1000)

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


class ExperimentUpdate(BaseModel):
    round_number: Optional[int] = Field(None, gt=0)
    notes: Optional[str] = Field(None, max_length=1000)
    review_status: Optional[str] = None


class ExperimentResponse(ExperimentBase):
    id: int
    config_id: int
    review_status: str
    total_time_s: Optional[float]
    total_water_l: Optional[float]
    flow_rate_lpm: Optional[float]
    avg_speed_rpm: Optional[float]
    is_abnormal: bool
    notes: str
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    time_points: List[TimePointResponse]

    class Config:
        from_attributes = True


class ExperimentReviewCreate(BaseModel):
    review_action: str = Field(..., pattern="^(approve|reject|recalculate)$")
    reviewer: Optional[str] = Field("", max_length=100)
    comment: Optional[str] = Field("", max_length=1000)


class ExperimentReviewResponse(BaseModel):
    id: int
    experiment_id: int
    review_action: str
    reviewer: str
    comment: str
    old_flow_rate: Optional[float]
    new_flow_rate: Optional[float]
    created_at: datetime

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
    notes: str
    speed_curve: List[dict]


class ComparisonData(BaseModel):
    config_id: int
    version: int
    bucket_diameter_m: float
    pulley_radius_m: float
    well_depth_m: float
    bucket_capacity_l: float
    avg_flow_rate_lpm: float
    avg_speed_rpm: float
    experiment_count: int
    experiments: List[EfficiencyData]


class WellComparisonData(BaseModel):
    well_id: int
    well_name: str
    location: str
    dynasty: str
    avg_flow_rate_lpm: float
    avg_speed_rpm: float
    experiment_count: int
    config_count: int
    latest_config: Optional[WellConfigResponse] = None


class EfficiencyPredictionInput(BaseModel):
    well_depth_m: float = Field(..., gt=0)
    bucket_capacity_l: float = Field(..., gt=0)
    bucket_diameter_m: float = Field(..., gt=0)
    pulley_radius_m: float = Field(..., gt=0)
    target_rpm: Optional[float] = Field(None, gt=0, description="目标转速(rpm)，不填则使用历史平均")


class EfficiencyPredictionResponse(BaseModel):
    predicted_flow_rate_lpm: float
    predicted_time_per_bucket_s: float
    predicted_liters_per_hour: float
    target_rpm: float
    bucket_cycles_per_minute: float
    confidence: float
    factors: dict


class ImportExportLogResponse(BaseModel):
    id: int
    well_id: Optional[int]
    operation_type: str
    file_name: str
    record_count: int
    operator: str
    status: str
    error_message: str
    created_at: datetime

    class Config:
        from_attributes = True


class ExperimentReportCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    config_id: Optional[int] = None
    author: Optional[str] = Field("", max_length=100)
    summary: Optional[str] = ""
    conclusions: Optional[str] = ""


class ExperimentReportResponse(BaseModel):
    id: int
    well_id: int
    config_id: Optional[int]
    title: str
    author: str
    summary: str
    conclusions: str
    report_content: str
    experiment_count: int
    avg_flow_rate_lpm: float
    avg_speed_rpm: float
    created_at: datetime

    class Config:
        from_attributes = True


class CSVExperimentRow(BaseModel):
    round_number: int
    point_index: int
    time_s: float
    water_l: float
