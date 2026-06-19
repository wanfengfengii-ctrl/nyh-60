import urllib.request
import json

url = "http://localhost:8001/wells/1/hydro-experiments"
data = {
    "meta": {
        "experiment_name": "春季-晴天-测试实验",
        "season": "春季",
        "weather": "晴天",
        "underground_water_level_m": 3.2,
        "well_water_temp_c": 14.5,
        "water_quality": "清澈",
        "draw_frequency": 3,
        "observation_date": "2026-03-15",
        "notes": "测试用实验数据"
    },
    "data_points": [
        {"point_index": 0, "elapsed_min": 0, "water_level_m": 3.2, "water_temp_c": 14.5, "flow_rate_lpm": 12.5, "draw_efficiency_pct": 85, "labor_burden_score": 3.0, "stability_index": 0.95},
        {"point_index": 1, "elapsed_min": 5, "water_level_m": 3.1, "water_temp_c": 14.6, "flow_rate_lpm": 11.8, "draw_efficiency_pct": 82, "labor_burden_score": 3.5, "stability_index": 0.92},
        {"point_index": 2, "elapsed_min": 10, "water_level_m": 3.0, "water_temp_c": 14.8, "flow_rate_lpm": 10.5, "draw_efficiency_pct": 75, "labor_burden_score": 4.2, "stability_index": 0.88},
        {"point_index": 3, "elapsed_min": 15, "water_level_m": 2.9, "water_temp_c": 15.0, "flow_rate_lpm": 9.2, "draw_efficiency_pct": 68, "labor_burden_score": 5.0, "stability_index": 0.82},
        {"point_index": 4, "elapsed_min": 20, "water_level_m": 2.8, "water_temp_c": 15.2, "flow_rate_lpm": 8.1, "draw_efficiency_pct": 60, "labor_burden_score": 5.8, "stability_index": 0.75},
        {"point_index": 5, "elapsed_min": 25, "water_level_m": 2.7, "water_temp_c": 15.3, "flow_rate_lpm": 7.2, "draw_efficiency_pct": 52, "labor_burden_score": 6.5, "stability_index": 0.70}
    ]
}

req = urllib.request.Request(
    url,
    data=json.dumps(data).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read())
        print("创建结果:", json.dumps(result, ensure_ascii=False, indent=2))
except Exception as e:
    print("错误:", e)
    if hasattr(e, 'read'):
        print("响应:", e.read().decode('utf-8'))
