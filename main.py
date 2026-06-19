import csv
import io
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote
from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import ValidationError

from database import get_db, init_db
from schemas import (
    WellCreate, WellUpdate,
    WellConfigCreate,
    ExperimentCreate, ExperimentUpdate,
    TimePointCreate, EfficiencyData, ComparisonData,
    WellComparisonData, EfficiencyPredictionInput,
    ExperimentReviewCreate, ExperimentReportCreate
)
from crud import (
    get_wells, get_well, create_well, update_well, delete_well,
    get_active_config, get_all_configs, get_config, create_config, activate_config,
    get_config_change_logs,
    get_experiments, get_experiment, create_experiment, update_experiment,
    update_experiment_time_points, delete_experiment,
    get_all_pending_reviews, get_pending_reviews_for_well,
    review_experiment, recalculate_all_for_config, get_experiment_reviews,
    get_import_export_logs, create_import_export_log,
    get_reports, get_report, create_report, delete_report,
    predict_well_efficiency
)
from calculator import calculate_experiment_efficiency

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="古井汲水效率复原平台 - 二期升级版")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
async def startup_event():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    wells = get_wells(db)
    pending_count = len(get_all_pending_reviews(db))
    return templates.TemplateResponse("index.html", {"request": request, "wells": wells, "pending_count": pending_count})


@app.get("/review-center", response_class=HTMLResponse)
async def review_center_page(request: Request, db: Session = Depends(get_db)):
    pending_experiments = get_all_pending_reviews(db)
    return templates.TemplateResponse("review_center.html", {
        "request": request,
        "pending_experiments": pending_experiments
    })


@app.get("/comparison", response_class=HTMLResponse)
async def comparison_page(request: Request, db: Session = Depends(get_db)):
    wells = get_wells(db)
    return templates.TemplateResponse("comparison.html", {"request": request, "wells": wells})


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, db: Session = Depends(get_db)):
    reports = get_reports(db)
    wells = get_wells(db)
    return templates.TemplateResponse("reports.html", {"request": request, "reports": reports, "wells": wells})


@app.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail_page(request: Request, report_id: int, db: Session = Depends(get_db)):
    report = get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    well = get_well(db, report.well_id)
    return templates.TemplateResponse("report_detail.html", {
        "request": request,
        "report": report,
        "well": well
    })


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
    pending_count = len(get_pending_reviews_for_well(db, well_id))
    reports = get_reports(db, well_id=well_id)
    if active_config:
        experiments = get_experiments(db, active_config.id)
    return templates.TemplateResponse("well_detail.html", {
        "request": request,
        "well": well,
        "active_config": active_config,
        "all_configs": all_configs,
        "experiments": experiments,
        "pending_count": pending_count,
        "reports": reports
    })


@app.get("/wells/{well_id}/config-versions", response_class=HTMLResponse)
async def config_versions_page(request: Request, well_id: int, db: Session = Depends(get_db)):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")
    all_configs = get_all_configs(db, well_id)
    config_logs = {}
    for cfg in all_configs:
        config_logs[cfg.id] = get_config_change_logs(db, cfg.id)
    return templates.TemplateResponse("config_versions.html", {
        "request": request,
        "well": well,
        "all_configs": all_configs,
        "config_logs": config_logs
    })


@app.post("/wells/{well_id}/config")
async def create_config_endpoint(
    well_id: int,
    well_depth_m: float = Form(...),
    bucket_capacity_l: float = Form(...),
    bucket_diameter_m: float = Form(...),
    pulley_radius_m: float = Form(...),
    change_note: str = Form(""),
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
            pulley_radius_m=pulley_radius_m,
            change_note=change_note
        )
    except ValidationError as e:
        errors = "; ".join([err["msg"] for err in e.errors()])
        return HTMLResponse(content=f"<div class='error'>参数错误: {errors}</div>", status_code=400)
    create_config(db, well_id, data)
    return RedirectResponse(url=f"/wells/{well_id}/config-versions", status_code=303)


@app.post("/wells/{well_id}/config/{config_id}/activate")
async def activate_config_endpoint(well_id: int, config_id: int, db: Session = Depends(get_db)):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")
    config = activate_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="参数配置不存在")
    if config.well_id != well_id:
        raise HTTPException(status_code=400, detail="参数配置不属于该古井")
    return RedirectResponse(url=f"/wells/{well_id}/config-versions", status_code=303)


@app.get("/api/configs/{config_id}/change-logs")
async def get_config_change_logs_api(config_id: int, db: Session = Depends(get_db)):
    config = get_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="参数配置不存在")
    logs = get_config_change_logs(db, config_id)
    return JSONResponse({"logs": [
        {
            "id": log.id,
            "field_name": log.field_name,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "change_reason": log.change_reason,
            "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else None
        } for log in logs
    ]})


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

    notes = form_data.get("notes", "")

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
        exp_data = ExperimentCreate(round_number=round_number, time_points=time_points, notes=notes)
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


@app.get("/api/experiments/{exp_id}")
async def get_experiment_api(exp_id: int, db: Session = Depends(get_db)):
    exp = get_experiment(db, exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    return JSONResponse({
        "id": exp.id,
        "round_number": exp.round_number,
        "notes": exp.notes,
        "review_status": exp.review_status,
        "time_points": [
            {
                "id": tp.id,
                "point_index": tp.point_index,
                "time_s": tp.time_s,
                "water_l": tp.water_l
            } for tp in exp.time_points
        ]
    })


@app.put("/api/experiments/{exp_id}")
async def update_experiment_api(
    exp_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    exp = get_experiment(db, exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    config = get_config(db, exp.config_id)
    if not config:
        raise HTTPException(status_code=404, detail="参数配置不存在")

    body = await request.json()

    try:
        update_data = ExperimentUpdate(**body.get("meta", {}))
    except ValidationError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    time_points_data = body.get("time_points", [])

    try:
        if update_data.round_number and update_data.round_number != exp.round_number:
            existing = get_experiment_by_round_wrapper(db, config.id, update_data.round_number)
            if existing and existing.id != exp_id:
                return JSONResponse({"success": False, "error": "该轮次已存在"}, status_code=400)

        if time_points_data:
            max_water = max(tp["water_l"] for tp in time_points_data)
            if max_water > config.bucket_capacity_l:
                return JSONResponse({"success": False, "error": f"出水量({max_water}L)超过桶容量({config.bucket_capacity_l}L)"}, status_code=400)
            times = [tp["time_s"] for tp in time_points_data]
            for i in range(1, len(times)):
                if times[i] <= times[i - 1]:
                    return JSONResponse({"success": False, "error": f"时间点必须严格递增：第{i+1}个时间点({times[i]})不大于第{i}个({times[i-1]})"}, status_code=400)
            if len(time_points_data) < 2:
                return JSONResponse({"success": False, "error": "至少需要2个时间点"}, status_code=400)

        if update_data.model_dump(exclude_unset=True):
            exp = update_experiment(db, exp, update_data, config)

        if time_points_data:
            exp = update_experiment_time_points(db, exp, time_points_data, config)

        return JSONResponse({"success": True, "experiment_id": exp.id})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)


def get_experiment_by_round_wrapper(db, config_id, round_number):
    from crud import get_experiment_by_round
    return get_experiment_by_round(db, config_id, round_number)


@app.post("/wells/{well_id}/experiments/{exp_id}/delete")
async def delete_experiment_endpoint(well_id: int, exp_id: int, db: Session = Depends(get_db)):
    config = get_active_config(db, well_id)
    if not config:
        raise HTTPException(status_code=404, detail="未找到配置")
    if not delete_experiment(db, exp_id, config):
        raise HTTPException(status_code=404, detail="实验记录不存在")
    return RedirectResponse(url=f"/wells/{well_id}", status_code=303)


@app.post("/api/experiments/{exp_id}/review")
async def review_experiment_api(
    exp_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    exp = get_experiment(db, exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    config = get_config(db, exp.config_id)
    if not config:
        raise HTTPException(status_code=404, detail="参数配置不存在")

    body = await request.json()
    try:
        review_data = ExperimentReviewCreate(**body)
    except ValidationError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    review_experiment(db, exp, config, review_data)
    return JSONResponse({"success": True, "review_status": exp.review_status})


@app.get("/api/experiments/{exp_id}/reviews")
async def get_experiment_reviews_api(exp_id: int, db: Session = Depends(get_db)):
    exp = get_experiment(db, exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    reviews = get_experiment_reviews(db, exp_id)
    return JSONResponse({"reviews": [
        {
            "id": r.id,
            "review_action": r.review_action,
            "reviewer": r.reviewer,
            "comment": r.comment,
            "old_flow_rate": r.old_flow_rate,
            "new_flow_rate": r.new_flow_rate,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None
        } for r in reviews
    ]})


@app.post("/wells/{well_id}/config/{config_id}/recalculate")
async def recalculate_all_endpoint(well_id: int, config_id: int, db: Session = Depends(get_db)):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")
    config = get_config(db, config_id)
    if not config or config.well_id != well_id:
        raise HTTPException(status_code=404, detail="参数配置不存在")
    count = recalculate_all_for_config(db, config)
    return JSONResponse({"success": True, "recalculated": count})


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
            notes=exp.notes or "",
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
                notes=exp.notes or "",
                speed_curve=speed_curve
            ).model_dump())

        avg_flow = sum(flow_rates) / len(flow_rates) if flow_rates else 0
        avg_speed = sum(speeds) / len(speeds) if speeds else 0

        result.append(ComparisonData(
            config_id=cfg.id,
            version=cfg.version,
            bucket_diameter_m=cfg.bucket_diameter_m,
            pulley_radius_m=cfg.pulley_radius_m,
            well_depth_m=cfg.well_depth_m,
            bucket_capacity_l=cfg.bucket_capacity_l,
            avg_flow_rate_lpm=round(avg_flow, 2),
            avg_speed_rpm=round(avg_speed, 2),
            experiment_count=len(experiments),
            experiments=exp_data_list
        ).model_dump())

    return JSONResponse({"configs": result})


@app.get("/api/wells/comparison")
async def get_multi_well_comparison_api(
    well_ids: str = Query(..., description="逗号分隔的古井ID列表"),
    db: Session = Depends(get_db)
):
    ids = [int(x.strip()) for x in well_ids.split(",") if x.strip().isdigit()]
    result = []
    for wid in ids:
        well = get_well(db, wid)
        if not well:
            continue
        all_configs = get_all_configs(db, wid)
        total_exp = 0
        flow_rates = []
        speeds = []
        for cfg in all_configs:
            exps = get_experiments(db, cfg.id)
            total_exp += len(exps)
            for e in exps:
                if e.review_status == "valid":
                    if e.flow_rate_lpm:
                        flow_rates.append(e.flow_rate_lpm)
                    if e.avg_speed_rpm:
                        speeds.append(e.avg_speed_rpm)
        avg_flow = round(sum(flow_rates) / len(flow_rates), 2) if flow_rates else 0
        avg_speed = round(sum(speeds) / len(speeds), 2) if speeds else 0
        active_cfg = get_active_config(db, wid)
        from schemas import WellConfigResponse
        result.append(WellComparisonData(
            well_id=well.id,
            well_name=well.name,
            location=well.location or "",
            dynasty=well.dynasty or "",
            avg_flow_rate_lpm=avg_flow,
            avg_speed_rpm=avg_speed,
            experiment_count=total_exp,
            config_count=len(all_configs),
            latest_config=WellConfigResponse.model_validate(active_cfg) if active_cfg else None
        ).model_dump(mode='json'))
    return JSONResponse({"wells": result})


@app.post("/api/wells/{well_id}/predict")
async def predict_efficiency_api(
    well_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")
    body = await request.json()
    try:
        data = EfficiencyPredictionInput(**body)
    except ValidationError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    result = predict_well_efficiency(
        db, well_id,
        data.well_depth_m, data.bucket_capacity_l,
        data.bucket_diameter_m, data.pulley_radius_m,
        data.target_rpm
    )
    return JSONResponse({"success": True, "prediction": result})


@app.get("/wells/{well_id}/export.csv")
async def export_experiments_csv(well_id: int, db: Session = Depends(get_db)):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["轮次", "时间点序号", "时间(秒)", "出水量(升)", "计算转速(rpm)", "状态", "备注"])

    all_configs = get_all_configs(db, well_id)
    count = 0
    for cfg in all_configs:
        for exp in get_experiments(db, cfg.id):
            for tp in exp.time_points:
                writer.writerow([
                    exp.round_number,
                    tp.point_index,
                    tp.time_s,
                    tp.water_l,
                    tp.calculated_speed_rpm or "",
                    exp.review_status,
                    exp.notes or ""
                ])
                count += 1

    create_import_export_log(db, {
        "well_id": well_id,
        "operation_type": "export",
        "file_name": f"{well.name}_实验数据.csv",
        "record_count": count,
        "status": "success"
    })

    output.seek(0)
    safe_filename = quote(f"{well.name}_实验数据.csv")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}"}
    )


@app.post("/wells/{well_id}/import.csv")
async def import_experiments_csv(
    well_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    well = get_well(db, well_id)
    if not well:
        return JSONResponse({"success": False, "error": "古井档案不存在"}, status_code=404)
    config = get_active_config(db, well_id)
    if not config:
        return JSONResponse({"success": False, "error": "请先配置辘轳结构参数"}, status_code=400)

    try:
        content = await file.read()
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        rounds_data = {}
        for row in reader:
            try:
                rn = int(row.get("轮次") or row.get("round_number", 0))
                pi = int(row.get("时间点序号") or row.get("point_index", 0))
                ts = float(row.get("时间(秒)") or row.get("time_s", 0))
                wl = float(row.get("出水量(升)") or row.get("water_l", 0))
            except (ValueError, TypeError):
                continue
            if rn not in rounds_data:
                rounds_data[rn] = []
            rounds_data[rn].append({"point_index": pi, "time_s": ts, "water_l": wl})

        imported = 0
        skipped = 0
        errors = []

        for rn, tps in rounds_data.items():
            if len(tps) < 2:
                skipped += 1
                continue
            tps.sort(key=lambda x: x["point_index"])
            max_water = max(t["water_l"] for t in tps)
            if max_water > config.bucket_capacity_l:
                errors.append(f"第{rn}轮：出水量超过桶容量")
                skipped += 1
                continue
            times = [t["time_s"] for t in tps]
            valid_time = True
            for i in range(1, len(times)):
                if times[i] <= times[i - 1]:
                    valid_time = False
                    break
            if not valid_time:
                errors.append(f"第{rn}轮：时间点未严格递增")
                skipped += 1
                continue

            from crud import get_experiment_by_round
            existing = get_experiment_by_round(db, config.id, rn)
            if existing:
                skipped += 1
                continue

            try:
                from schemas import ExperimentCreate, TimePointCreate
                tps_schema = [TimePointCreate(**t) for t in tps]
                exp_data = ExperimentCreate(round_number=rn, time_points=tps_schema)
                exp = create_experiment(db, config, exp_data)
                if exp:
                    imported += 1
            except Exception as e:
                errors.append(f"第{rn}轮：{str(e)}")
                skipped += 1

        create_import_export_log(db, {
            "well_id": well_id,
            "operation_type": "import",
            "file_name": file.filename,
            "record_count": imported,
            "status": "success" if imported > 0 else "failed",
            "error_message": "; ".join(errors) if errors else ""
        })

        return JSONResponse({
            "success": True,
            "imported": imported,
            "skipped": skipped,
            "errors": errors
        })

    except Exception as e:
        create_import_export_log(db, {
            "well_id": well_id,
            "operation_type": "import",
            "file_name": file.filename or "unknown.csv",
            "record_count": 0,
            "status": "failed",
            "error_message": str(e)
        })
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/wells/{well_id}/reports")
async def create_report_endpoint(
    well_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    well = get_well(db, well_id)
    if not well:
        raise HTTPException(status_code=404, detail="古井档案不存在")

    form_data = await request.form()
    try:
        report_data = ExperimentReportCreate(
            title=form_data.get("title", ""),
            config_id=int(form_data.get("config_id", 0)) if form_data.get("config_id") else None,
            author=form_data.get("author", ""),
            summary=form_data.get("summary", ""),
            conclusions=form_data.get("conclusions", "")
        )
    except ValidationError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    config = None
    experiments = []
    if report_data.config_id:
        config = get_config(db, report_data.config_id)
        if config and config.well_id == well_id:
            experiments = get_experiments(db, config.id)
    if not experiments:
        active_cfg = get_active_config(db, well_id)
        if active_cfg:
            config = active_cfg
            experiments = get_experiments(db, active_cfg.id)

    if not experiments:
        return JSONResponse({"success": False, "error": "暂无实验数据可生成报告"}, status_code=400)

    report = create_report(db, well, config, experiments, report_data)
    return RedirectResponse(url=f"/reports/{report.id}", status_code=303)


@app.post("/reports/{report_id}/delete")
async def delete_report_endpoint(report_id: int, db: Session = Depends(get_db)):
    report = get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    well_id = report.well_id
    delete_report(db, report_id)
    return RedirectResponse(url=f"/wells/{well_id}", status_code=303)


@app.get("/reports/{report_id}/print", response_class=HTMLResponse)
async def print_report_page(request: Request, report_id: int, db: Session = Depends(get_db)):
    report = get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    well = get_well(db, report.well_id)
    return templates.TemplateResponse("report_print.html", {
        "request": request,
        "report": report,
        "well": well
    })


@app.get("/api/import-export-logs")
async def get_import_export_logs_api(db: Session = Depends(get_db)):
    logs = get_import_export_logs(db)
    return JSONResponse({"logs": [
        {
            "id": log.id,
            "well_id": log.well_id,
            "operation_type": log.operation_type,
            "file_name": log.file_name,
            "record_count": log.record_count,
            "operator": log.operator,
            "status": log.status,
            "error_message": log.error_message,
            "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else None
        } for log in logs
    ]})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
