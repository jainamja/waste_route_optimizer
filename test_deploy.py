from waste_route_optimizer import app, db, SavedTemplate
import json

with app.test_client() as client:
    with app.app_context():
        res = client.post('/api/deploy_template/4?mode=deploy')
        print("Status:", res.status_code)
        if res.status_code == 500:
            print("Response:", res.text)
