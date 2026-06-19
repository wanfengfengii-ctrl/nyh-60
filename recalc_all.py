import urllib.request
import json

exp_ids = [1, 2, 4, 5]
for exp_id in exp_ids:
    url = f'http://127.0.0.1:8000/api/hydro-experiments/{exp_id}/recalculate'
    req = urllib.request.Request(url, data=b'', method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            aid = result.get('analysis_id')
            print(f'实验 {exp_id} 重新计算成功: 分析ID={aid}')
    except Exception as e:
        print(f'实验 {exp_id} 重新计算失败: {e}')
