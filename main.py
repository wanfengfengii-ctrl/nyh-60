from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import ValidationError

from database import get_db, init_db
from schemas import (
    WellCreate, WellUpdate,
    WellConfigCreate,
    ExperimentCreate, TimePointCreate,
    EfficiencyData, ComparisonData
)
from crud import (
    get_wells, get_well, create_well, update_well, delete_well,
    get_active_config, get_all_configs, create_config,
    get_experiments, get_experiment, create_experiment, delete_experiment
)
from calculator import calculate_experiment_efficiency

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="古井汲水效率复原平台")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
async def startup_event():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    wells = get_wells(db)
    return templates.TemplateResponse("index.html", {"request": request, "wells": wells})


@app.post("/wells")
async def create_well_endpoint(
    request: Request,
    name: str = Form(...),
    location: str = Form(""),
    dynasty: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    try:
        data = WellCreate(name=name, location=location, dynasty=dynasty, description=description)
    except ValidationError as e:
        return HTMLResponse(content=f"<div class='error'>{str(e)}</div>", status_code=400)
    create_well(db, data)
    return RedirectResponse(url="/", status_code=303)


@app.post("/wells/{well_id}/delete")
async def delete_well_endpoint(well_id: int, db: Session = Depends(get_db)):
    if not delete_well(db, well_id):
        raise HTTPException(status_code=404, detail="古井档案不存在")
    return RedirectResponse(url="/", status_code=303)


@app.get("/wells/{well_id}", response_class=HTMLResponse)
async def well_detail(request: Request, well_id: int, db: Session = Depends(get_db)):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")
    active_config = get_active_config(db, well_id)
    all_configs = get_all_configs(db, well_id)
    experiments = []
    if active_config:
        experiments = get_experiments(db, active_config.id)
    return templates.TemplateResponse("well_detail.html", {
        "request": request,
        "well": well,
        "active_config": active_config,
        "all_configs": all_configs,
        "experiments": experiments
    })


@app.post("/wells/{well_id}/config")
async def create_config_endpoint(
    well_id: int,
    well_depth_m: float = Form(...),
    bucket_capacity_l: float = Form(...),
    bucket_diameter_m: float = Form(...),
    pulley_radius_m: float = Form(...),
    db: Session = Depends(get_db)
):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")
    try:
        data = WellConfigCreate(
            well_depth_m=well_depth_m,
            bucket_capacity_l=bucket_capacity_l,
            bucket_diameter_m=bucket_diameter_m,
            pulley_radius_m=pulley_radius_m
        )
    except ValidationError as e:
        errors = "; ".join([err["msg"] for err in e.errors()])
        return HTMLResponse(content=f"<div class='error'>参数错误: {errors}</div>", status_code=400)
    create_config(db, well_id, data)
    return RedirectResponse(url=f"/wells/{well_id}", status_code=303)


def extract_index(key: str) -> int:
    return int(key.rsplit("_", 1)[-1])


@app.post("/wells/{well_id}/experiments")
async def create_experiment_endpoint(
    well_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    well = get_well(db, well_id)
    if not well:
        return JSONResponse({"success": False, "error": "古井档案不存在"}, status_code=404)
    config = get_active_config(db, well_id)
    if not config:
        return JSONResponse({"success": False, "error": "请先配置辘轳结构参数"}, status_code=400)

    form_data = await request.form()

    try:
        round_number = int(form_data.get("round_number", 0))
    except (ValueError, TypeError):
        return JSONResponse({"success": False, "error": "轮次必须是正整数"}, status_code=400)

    time_point_keys = sorted(
        [k for k in form_data.keys() if k.startswith("time_")],
        key=extract_index
    )
    water_point_keys = sorted(
        [k for k in form_data.keys() if k.startswith("water_")],
        key=extract_index
    )

    if len(time_point_keys) != len(water_point_keys):
        return JSONResponse({"success": False, "error": "时间点和出水量数据不匹配"}, status_code=400)

    time_points = []
    for i in range(len(time_point_keys)):
        try:
            t = float(form_data.get(time_point_keys[i], ""))
            w = float(form_data.get(water_point_keys[i], ""))
            time_points.append(TimePointCreate(point_index=i, time_s=t, water_l=w))
        except (ValueError, TypeError):
            return JSONResponse({"success": False, "error": f"第{i+1}个时间点数据格式错误"}, status_code=400)

    try:
        exp_data = ExperimentCreate(round_number=round_number, time_points=time_points)
    except ValidationError as e:
        errors = "; ".join([err["msg"] for err in e.errors()])
        return JSONResponse({"success": False, "error": f"数据错误: {errors}"}, status_code=400)

    try:
        exp = create_experiment(db, config, exp_data)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    if exp is None:
        return JSONResponse({"success": False, "error": f"第{round_number}轮实验已存在"}, status_code=400)

    return JSONResponse({"success": True, "redirect": f"/wells/{well_id}"})


@app.post("/wells/{well_id}/experiments/{exp_id}/delete")
async def delete_experiment_endpoint(well_id: int, exp_id: int, db: Session = Depends(get_db)):
    config = get_active_config(db, well_id)
    if not config:
        raise HTTPException(status_code=404, detail="未找到配置")
    if not delete_experiment(db, exp_id, config):
        raise HTTPException(status_code=404, detail="实验记录不存在")
    return RedirectResponse(url=f"/wells/{well_id}", status_code=303)


@app.get("/api/wells/{well_id}/efficiency")
async def get_efficiency_api(well_id: int, db: Session = Depends(get_db)):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")
    config = get_active_config(db, well_id)
    if not config:
        return JSONResponse({"experiments": []})

    experiments = get_experiments(db, config.id)
    result = []
    for exp in experiments:
        _, _, _, _, speed_curve = calculate_experiment_efficiency(exp, config)
        result.append(EfficiencyData(
            experiment_id=exp.id,
            round_number=exp.round_number,
            total_time_s=exp.total_time_s or 0,
            total_water_l=exp.total_water_l or 0,
            flow_rate_lpm=exp.flow_rate_lpm or 0,
            avg_speed_rpm=exp.avg_speed_rpm or 0,
            is_abnormal=exp.is_abnormal,
            review_status=exp.review_status,
            speed_curve=speed_curve
        ).model_dump())

    return JSONResponse({"experiments": result})


@app.get("/api/wells/{well_id}/comparison")
async def get_comparison_api(well_id: int, db: Session = Depends(get_db)):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")
    all_configs = get_all_configs(db, well_id)
    result = []

    for cfg in all_configs:
        experiments = get_experiments(db, cfg.id)
        if not experiments:
            continue
        exp_data_list = []
        flow_rates = []
        speeds = []
        for exp in experiments:
            _, _, _, _, speed_curve = calculate_experiment_efficiency(exp, cfg)
            if exp.flow_rate_lpm:
                flow_rates.append(exp.flow_rate_lpm)
            if exp.avg_speed_rpm:
                speeds.append(exp.avg_speed_rpm)
            exp_data_list.append(EfficiencyData(
                experiment_id=exp.id,
                round_number=exp.round_number,
                total_time_s=exp.total_time_s or 0,
                total_water_l=exp.total_water_l or 0,
                flow_rate_lpm=exp.flow_rate_lpm or 0,
                avg_speed_rpm=exp.avg_speed_rpm or 0,
                is_abnormal=exp.is_abnormal,
                review_status=exp.review_status,
                speed_curve=speed_curve
            ).model_dump())

        avg_flow = sum(flow_rates) / len(flow_rates) if flow_rates else 0
        avg_speed = sum(speeds) / len(speeds) if speeds else 0

        result.append(ComparisonData(
            config_id=cfg.id,
            bucket_diameter_m=cfg.bucket_diameter_m,
            pulley_radius_m=cfg.pulley_radius_m,
            well_depth_m=cfg.well_depth_m,
            avg_flow_rate_lpm=round(avg_flow, 2),
            avg_speed_rpm=round(avg_speed, 2),
            experiment_count=len(experiments),
            experiments=exp_data_list
        ).model_dump())

    return JSONResponse({"configs": result})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
