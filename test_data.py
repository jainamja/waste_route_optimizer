from waste_route_optimizer import app

with app.test_client() as client:
    res = client.get('/api/data')
    data = res.get_json()
    print("Keys in /api/data:", data.keys())
    if 'metadata' in data:
        print("Metadata keys:", data['metadata'].keys())
