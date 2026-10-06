import requests
import json
import io

s = requests.Session()
BASE_URL = "http://127.0.0.1:5000"

res = s.post(f"{BASE_URL}/login", data={'username': 'admin', 'password': 'admin'})

dummy_csv = "Sr,Name,Address,Lat,Lng\n1,Cust 1,Address 1,23.0225,72.5714\n2,Cust 2,Address 2,23.03,72.58"

files = {'file': ('dummy.csv', io.StringIO(dummy_csv), 'text/csv')}
data = {
    'num_trucks': '2',
    'start_coords_json': json.dumps(["23.0225,72.5714", "23.0225,72.5714"]),
    'end_coords_json': json.dumps(["23.03,72.58", "23.03,72.58"])
}

res = s.post(f"{BASE_URL}/upload", files=files, data=data, allow_redirects=False)
print(f"Upload status: {res.status_code}")
if res.status_code == 302:
    print(f"Redirected to: {res.headers.get('Location')}")
else:
    print(res.text)

res = s.get(f"{BASE_URL}/api/data")
print(f"API data status: {res.status_code}")
try:
    data = res.json()
    print(f"Routes: {len(data.get('routes', []))}")
    print(f"Customers: {len(data.get('customers', []))}")
except Exception as e:
    print(f"Failed to parse JSON: {e}")
    print(res.text[:500])
