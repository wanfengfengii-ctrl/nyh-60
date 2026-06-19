import urllib.request
import json

url = "http://localhost:8001/api/hydro-experiments/1"

with urllib.request.urlopen(url) as response:
    result = json.loads(response.read())
    analysis = result.get("analysis_result", {})
    
    print("=== 水位趋势数据 ===")
    for i, item in enumerate(analysis.get("water_level_trend", [])):
        print(f"点{i}: keys={list(item.keys())}, values={item}")
    
    print("\n=== 分析结果字段 ===")
    print(f"字段列表: {list(analysis.keys())}")
    
    print("\n=== 高效时段 ===")
    print(json.dumps(analysis.get("high_efficiency_periods", []), ensure_ascii=False, indent=2))
    
    print("\n=== 低效时段 ===")
    print(json.dumps(analysis.get("low_efficiency_periods", []), ensure_ascii=False, indent=2))
