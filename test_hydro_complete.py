import urllib.request
import json

BASE_URL = "http://127.0.0.1:8000"

def test_create_experiment(well_id, name, season, weather, water_level, water_temp, quality, frequency, data_points):
    url = f"{BASE_URL}/wells/{well_id}/hydro-experiments"
    data = {
        "meta": {
            "experiment_name": name,
            "season": season,
            "weather": weather,
            "underground_water_level_m": water_level,
            "well_water_temp_c": water_temp,
            "water_quality": quality,
            "draw_frequency": frequency,
            "observation_date": "2024-06-15",
            "notes": f"测试实验 - {season}"
        },
        "data_points": data_points
    }
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            print(f"创建实验 '{name}' 成功: ID={result.get('experiment_id')}")
            return result.get('experiment_id')
    except Exception as e:
        print(f"创建实验 '{name}' 失败: {e}")
        if hasattr(e, 'read'):
            print(f"  响应: {e.read().decode('utf-8')}")
        return None

def test_get_experiment(exp_id):
    url = f"{BASE_URL}/api/hydro-experiments/{exp_id}"
    try:
        with urllib.request.urlopen(url) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            print(f"\n=== 实验 {exp_id} 详情 ===")
            print(f"  实验名称: {result.get('experiment_name')}")
            print(f"  季节: {result.get('season')}")
            
            analysis = result.get('analysis_result', {})
            if analysis:
                print(f"  平均流量: {analysis.get('avg_flow_rate')} L/min")
                print(f"  峰值流量: {analysis.get('peak_flow')} L/min")
                print(f"  环境敏感性: {analysis.get('env_sensitivity')}")
                print(f"  稳定性指数: {analysis.get('stability_index')}")
                print(f"  人工负荷: {analysis.get('labor_burden')}")
                print(f"  综合评分: {analysis.get('overall_score')}")
                print(f"  温度-效率相关: {analysis.get('temp_efficiency_corr')}")
                print(f"  水位-效率相关: {analysis.get('level_efficiency_corr')}")
                
                high_periods = analysis.get('high_efficiency_periods', [])
                low_periods = analysis.get('low_efficiency_periods', [])
                print(f"  高效时段数: {len(high_periods)}")
                for i, p in enumerate(high_periods[:3]):
                    print(f"    - 时段{i+1}: {p.get('start_min')}-{p.get('end_min')}分钟, 平均效率: {p.get('avg_efficiency')}")
                
                print(f"  低效时段数: {len(low_periods)}")
                for i, p in enumerate(low_periods[:3]):
                    print(f"    - 时段{i+1}: {p.get('start_min')}-{p.get('end_min')}分钟, 平均效率: {p.get('avg_efficiency')}")
                
                anomalies = analysis.get('anomaly_list', [])
                print(f"  异常警告数: {len(anomalies)}")
                for w in anomalies[:3]:
                    print(f"    - {w.get('type')}: {w.get('message')}")
            else:
                print("  无分析结果")
            
            return result
    except Exception as e:
        print(f"获取实验详情失败: {e}")
        return None

def test_recalculate(exp_id):
    url = f"{BASE_URL}/api/hydro-experiments/{exp_id}/recalculate"
    req = urllib.request.Request(url, data=b'', method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            print(f"重新计算成功: 分析ID={result.get('analysis_id')}")
            return result
    except Exception as e:
        print(f"重新计算失败: {e}")
        return None

def test_create_comparison(well_id, name, experiment_ids):
    url = f"{BASE_URL}/api/wells/{well_id}/hydro-comparisons"
    data = {
        "period_name": name,
        "description": "测试对比周期",
        "experiment_ids": experiment_ids
    }
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            print(f"创建对比组成功: ID={result.get('period_id')}")
            return result.get('period_id')
    except Exception as e:
        print(f"创建对比组失败: {e}")
        return None

def test_get_comparison(period_id):
    url = f"{BASE_URL}/api/hydro-comparisons/{period_id}"
    try:
        with urllib.request.urlopen(url) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            print(f"\n=== 对比组 {period_id} 详情 ===")
            print(f"  对比组名称: {result.get('period_name')}")
            print(f"  描述: {result.get('description')}")
            
            items = result.get('items', [])
            print(f"  实验数量: {len(items)}")
            for item in items:
                exp = item.get('experiment', {})
                analysis = item.get('analysis_result', {})
                print(f"    - {exp.get('experiment_name')} ({exp.get('season')}): 评分={analysis.get('overall_score') if analysis else 'N/A'}")
            
            season_comp = result.get('season_comparison', {})
            print(f"  季节对比: {len(season_comp)} 个季节")
            for season, data in season_comp.items():
                print(f"    - {season}: 实验数={data.get('experiment_count')}, 平均流量={data.get('avg_flow_rate')} L/min, 评分={data.get('overall_score')}")
            
            return result
    except Exception as e:
        print(f"获取对比结果失败: {e}")
        return None

def generate_data_points(base_flow, variation, count=12):
    points = []
    for i in range(count):
        elapsed = i * 5
        flow = base_flow + variation * ((i % 3) - 1)
        if i > 8:
            flow *= 0.85
        level = 10.0 - 0.1 * i
        temp = 15.0 + 0.05 * i
        eff = min(95, max(30, (flow / base_flow) * 70 + (i % 5) * 3))
        labor = 3.0 + (i % 4) * 1.5
        stability = 0.9 - (i % 3) * 0.1
        
        points.append({
            "point_index": i,
            "elapsed_min": elapsed,
            "water_level_m": round(level, 2),
            "water_temp_c": round(temp, 2),
            "flow_rate_lpm": round(flow, 2),
            "draw_efficiency_pct": round(eff, 1),
            "labor_burden_score": round(labor, 1),
            "stability_index": round(stability, 3)
        })
    return points

if __name__ == "__main__":
    print("=== 水文环境模块完整功能测试 ===\n")
    
    well_id = 1
    
    print("--- 第1步: 创建多个不同季节的实验 ---")
    exp_ids = []
    
    spring_points = generate_data_points(12.5, 1.5)
    exp_id = test_create_experiment(well_id, "春季枯水期实验", "春季", "晴天", 9.8, 14.5, "清澈", 2, spring_points)
    if exp_id:
        exp_ids.append(exp_id)
    
    summer_points = generate_data_points(18.0, 2.5)
    exp_id = test_create_experiment(well_id, "夏季丰水期实验", "夏季", "雨天", 12.5, 18.0, "微浊", 5, summer_points)
    if exp_id:
        exp_ids.append(exp_id)
    
    autumn_points = generate_data_points(15.0, 2.0)
    exp_id = test_create_experiment(well_id, "秋季平水期实验", "秋季", "多云", 11.0, 16.0, "清澈", 3, autumn_points)
    if exp_id:
        exp_ids.append(exp_id)
    
    winter_points = generate_data_points(10.0, 1.0)
    exp_id = test_create_experiment(well_id, "冬季枯水期实验", "冬季", "雪天", 8.5, 8.0, "清澈", 1, winter_points)
    if exp_id:
        exp_ids.append(exp_id)
    
    print(f"\n共创建 {len(exp_ids)} 个实验")
    
    if len(exp_ids) > 0:
        print("\n--- 第2步: 验证实验详情和分析结果 ---")
        test_get_experiment(exp_ids[0])
        
        print("\n--- 第3步: 测试重新计算 ---")
        test_recalculate(exp_ids[0])
        test_get_experiment(exp_ids[0])
        
        if len(exp_ids) >= 2:
            print("\n--- 第4步: 创建多周期对比 ---")
            comp_id = test_create_comparison(well_id, "四季水文对比", exp_ids)
            if comp_id:
                test_get_comparison(comp_id)
    
    print("\n=== 测试完成 ===")
