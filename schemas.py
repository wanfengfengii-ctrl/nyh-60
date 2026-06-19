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


class LaborTimePointBase(BaseModel):
    point_index: int = Field(..., ge=0)
    elapsed_min: float = Field(..., ge=0, description="累计时间必须大于等于0分钟")
    total_water_l: float = Field(..., ge=0, description="累计出水量必须大于等于0升")
    worker_rotation: Optional[int] = Field(0, ge=0, description="轮班次数，0表示无轮班")
    fatigue_level: Optional[float] = Field(0.0, ge=0, le=1, description="疲劳等级0~1")
    is_rest_period: Optional[bool] = False


class LaborTimePointCreate(LaborTimePointBase):
    pass


class LaborTimePointResponse(LaborTimePointBase):
    id: int
    instantaneous_flow_lpm: Optional[float] = None

    class Config:
        from_attributes = True


class LaborExperimentBase(BaseModel):
    experiment_name: str = Field(..., min_length=1, max_length=200)
    worker_count: int = Field(..., ge=1, description="参与人数必须大于等于1")
    work_mode: str = Field(..., pattern="^(单人独立|双人轮流|三人交替|多人协同|自定义)$", description="分工方式不合法")
    continuous_duration_min: float = Field(..., gt=0, description="连续作业时长必须大于0分钟")
    rest_interval_min: Optional[float] = Field(0.0, ge=0, description="休息间隔必须大于等于0分钟")
    fatigue_factor: Optional[float] = Field(0.0, ge=0, le=1, description="体力衰减系数0~1")
    notes: Optional[str] = Field("", max_length=5000)


class LaborExperimentCreate(LaborExperimentBase):
    config_id: Optional[int] = None
    time_points: List[LaborTimePointCreate]

    @field_validator("time_points")
    @classmethod
    def validate_time_points(cls, v):
        if len(v) < 3:
            raise ValueError("至少需要3个时间点数据用于效率分析")
        elapsed = [tp.elapsed_min for tp in v]
        for i in range(1, len(elapsed)):
            if elapsed[i] <= elapsed[i - 1]:
                raise ValueError(f"时间点必须严格递增：第{i+1}个时间点({elapsed[i]}min)不大于第{i}个({elapsed[i-1]}min)")
        waters = [tp.total_water_l for tp in v]
        for i in range(1, len(waters)):
            if waters[i] < waters[i - 1]:
                raise ValueError(f"累计出水量不能减少：第{i+1}个点({waters[i]}L)小于第{i}个({waters[i-1]}L)")
        return v


class LaborExperimentUpdate(BaseModel):
    experiment_name: Optional[str] = Field(None, min_length=1, max_length=200)
    worker_count: Optional[int] = Field(None, ge=1)
    work_mode: Optional[str] = Field(None, pattern="^(单人独立|双人轮流|三人交替|多人协同|自定义)$")
    continuous_duration_min: Optional[float] = Field(None, gt=0)
    rest_interval_min: Optional[float] = Field(None, ge=0)
    fatigue_factor: Optional[float] = Field(None, ge=0, le=1)
    notes: Optional[str] = Field(None, max_length=5000)


class LaborAnalysisResultResponse(BaseModel):
    id: int
    experiment_id: int
    total_water_l: float
    total_effective_min: float
    total_rest_min: float
    avg_flow_rate_lpm: float
    per_capita_flow_lpm: float
    peak_flow_rate_lpm: float
    peak_duration_min: float
    peak_start_min: float
    efficiency_decay_pct: float
    stability_cv: float
    fatigue_correlation: float
    work_rest_ratio: float
    anomaly_flags: str
    anomaly_list: Optional[List[dict]] = None

    class Config:
        from_attributes = True


class LaborExperimentResponse(LaborExperimentBase):
    id: int
    well_id: int
    config_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    time_points: List[LaborTimePointResponse]
    analysis_result: Optional[LaborAnalysisResultResponse] = None

    class Config:
        from_attributes = True


class LaborComparisonItemCreate(BaseModel):
    experiment_id: int = Field(..., gt=0)
    sort_order: Optional[int] = 0


class LaborComparisonGroupCreate(BaseModel):
    well_id: int = Field(..., gt=0)
    group_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field("", max_length=2000)
    items: List[LaborComparisonItemCreate]

    @field_validator("items")
    @classmethod
    def validate_items(cls, v):
        if len(v) < 2:
            raise ValueError("对比组至少需要2组实验数据")
        exp_ids = [item.experiment_id for item in v]
        if len(exp_ids) != len(set(exp_ids)):
            raise ValueError("对比组不能包含重复实验")
        return v


class LaborComparisonResult(BaseModel):
    group_id: int
    group_name: str
    description: str
    experiments: List[LaborExperimentResponse]
    synergy_analysis: Optional[dict] = None
    multi_round_comparison: Optional[dict] = None


class SceneConfigBase(BaseModel):
    config_name: str = Field(..., min_length=1, max_length=200)
    season: Optional[str] = Field("春季", pattern="^(春季|夏季|秋季|冬季)$")
    time_of_day: Optional[str] = Field("上午", pattern="^(清晨|上午|正午|下午|傍晚|夜间)$")
    temperature_c: Optional[float] = Field(20.0, ge=-30, le=50, description="气温(-30~50°C)")
    ground_condition: Optional[str] = Field("干燥坚实", pattern="^(干燥坚实|微湿防滑|泥泞湿滑|结冰光滑|沙石凹凸)$")
    humidity_pct: Optional[float] = Field(50.0, ge=0, le=100, description="湿度(0~100%)")
    wind_level: Optional[int] = Field(0, ge=0, le=12, description="风力等级(0~12)")
    water_level_m: Optional[float] = Field(0.0, ge=0, description="水位变化(m)")
    description: Optional[str] = Field("", max_length=2000)
    is_preset: Optional[bool] = False


class SceneConfigCreate(SceneConfigBase):
    pass


class SceneConfigUpdate(BaseModel):
    config_name: Optional[str] = Field(None, min_length=1, max_length=200)
    season: Optional[str] = Field(None, pattern="^(春季|夏季|秋季|冬季)$")
    time_of_day: Optional[str] = Field(None, pattern="^(清晨|上午|正午|下午|傍晚|夜间)$")
    temperature_c: Optional[float] = Field(None, ge=-30, le=50)
    ground_condition: Optional[str] = Field(None, pattern="^(干燥坚实|微湿防滑|泥泞湿滑|结冰光滑|沙石凹凸)$")
    humidity_pct: Optional[float] = Field(None, ge=0, le=100)
    wind_level: Optional[int] = Field(None, ge=0, le=12)
    water_level_m: Optional[float] = Field(None, ge=0)
    description: Optional[str] = Field(None, max_length=2000)


class SceneConfigResponse(SceneConfigBase):
    id: int
    well_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LaborSchemeBase(BaseModel):
    scheme_name: str = Field(..., min_length=1, max_length=200)
    worker_count: int = Field(..., ge=1, description="参与人数≥1")
    work_mode: str = Field(..., pattern="^(单人独立|双人轮流|三人交替|多人协同|自定义)$")
    continuous_duration_min: float = Field(..., gt=0, description="连续作业时长>0分钟")
    rest_interval_min: Optional[float] = Field(0.0, ge=0, description="休息间隔≥0分钟")
    rest_duration_min: Optional[float] = Field(5.0, ge=0, description="单次休息时长≥0分钟")
    shift_rotation: Optional[bool] = False
    shift_duration_min: Optional[float] = Field(15.0, gt=0, description="轮班时长>0分钟")
    base_fatigue_factor: Optional[float] = Field(0.1, ge=0, le=1, description="基础体力衰减系数0~1")
    recovery_rate: Optional[float] = Field(0.3, ge=0, le=1, description="恢复速率0~1")
    workload_intensity: Optional[str] = Field("中等", pattern="^(轻松|中等|较重|繁重)$")
    description: Optional[str] = Field("", max_length=2000)


class LaborSchemeCreate(LaborSchemeBase):
    pass


class LaborSchemeUpdate(BaseModel):
    scheme_name: Optional[str] = Field(None, min_length=1, max_length=200)
    worker_count: Optional[int] = Field(None, ge=1)
    work_mode: Optional[str] = Field(None, pattern="^(单人独立|双人轮流|三人交替|多人协同|自定义)$")
    continuous_duration_min: Optional[float] = Field(None, gt=0)
    rest_interval_min: Optional[float] = Field(None, ge=0)
    rest_duration_min: Optional[float] = Field(None, ge=0)
    shift_rotation: Optional[bool] = None
    shift_duration_min: Optional[float] = Field(None, gt=0)
    base_fatigue_factor: Optional[float] = Field(None, ge=0, le=1)
    recovery_rate: Optional[float] = Field(None, ge=0, le=1)
    workload_intensity: Optional[str] = Field(None, pattern="^(轻松|中等|较重|繁重)$")
    description: Optional[str] = Field(None, max_length=2000)


class LaborSchemeResponse(LaborSchemeBase):
    id: int
    well_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SimulationTimePointBase(BaseModel):
    point_index: int = Field(..., ge=0)
    elapsed_min: float = Field(..., ge=0)
    total_water_l: float = Field(0.0, ge=0)
    instantaneous_flow_lpm: float = Field(0.0, ge=0)
    avg_fatigue_level: float = Field(0.0, ge=0, le=1)
    active_worker_count: int = Field(0, ge=0)
    is_rest_period: bool = False
    efficiency_factor: float = Field(1.0, ge=0, le=2)


class SimulationTimePointResponse(SimulationTimePointBase):
    id: int

    class Config:
        from_attributes = True


class SceneSimulationBase(BaseModel):
    simulation_name: str = Field(..., min_length=1, max_length=200)
    simulation_duration_min: float = Field(120.0, gt=0, description="模拟时长>0分钟")
    time_step_min: float = Field(1.0, gt=0, description="时间步长>0分钟")


class SceneSimulationCreate(SceneSimulationBase):
    scene_config_id: Optional[int] = None
    labor_scheme_id: Optional[int] = None
    config_id: Optional[int] = None


class SceneSimulationResponse(SceneSimulationBase):
    id: int
    well_id: int
    total_water_l: float
    avg_flow_rate_lpm: float
    peak_flow_rate_lpm: float
    per_capita_flow_lpm: float
    efficiency_decay_pct: float
    final_fatigue_level: float
    avg_fatigue_level: float
    total_rest_min: float
    total_work_min: float
    work_rest_ratio: float
    stability_cv: float
    overall_score: float
    created_at: datetime
    time_points: List[SimulationTimePointResponse] = []

    class Config:
        from_attributes = True


class SceneSimulationRunRequest(BaseModel):
    well_id: int = Field(..., gt=0)
    scene_config_id: Optional[int] = None
    labor_scheme_id: Optional[int] = None
    config_id: Optional[int] = None
    simulation_name: str = Field(..., min_length=1, max_length=200)
    simulation_duration_min: float = Field(120.0, gt=0)
    time_step_min: float = Field(1.0, gt=0)


class OptimizationReportItemResponse(BaseModel):
    id: int
    report_id: int
    simulation_id: Optional[int] = None
    scene_config_id: Optional[int] = None
    labor_scheme_id: Optional[int] = None
    scene_name: str = ""
    scheme_name: str = ""
    avg_flow_rate_lpm: float = 0.0
    per_capita_flow_lpm: float = 0.0
    efficiency_decay_pct: float = 0.0
    overall_score: float = 0.0
    ranking: int = 0
    notes: str = ""

    class Config:
        from_attributes = True


class OptimizationReportBase(BaseModel):
    report_title: str = Field(..., min_length=1, max_length=200)
    author: Optional[str] = Field("", max_length=100)
    summary: Optional[str] = ""
    conclusions: Optional[str] = ""


class OptimizationReportCreate(OptimizationReportBase):
    scene_config_ids: Optional[List[int]] = None
    labor_scheme_ids: Optional[List[int]] = None
    config_id: Optional[int] = None
    simulation_duration_min: Optional[float] = Field(120.0, gt=0)


class OptimizationReportResponse(OptimizationReportBase):
    id: int
    well_id: int
    config_id: Optional[int] = None
    report_content: str = ""
    best_scheme_id: Optional[int] = None
    best_scheme_name: str = ""
    scene_count: int = 0
    scheme_count: int = 0
    recommendation: str = ""
    optimal_worker_count: Optional[int] = None
    optimal_work_mode: str = ""
    suggested_rest_rhythm: str = ""
    created_at: datetime
    items: List[OptimizationReportItemResponse] = []

    class Config:
        from_attributes = True
