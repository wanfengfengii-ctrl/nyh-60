import urllib.request
import json

url = "http://localhost:8001/api/hydro-experiments/1"

with urllib.request.urlopen(url) as response:
    result = json.loads(response.read())
    print("实验详情:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
