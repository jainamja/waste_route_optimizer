from waste_route_optimizer import app, db, SavedTemplate

with app.test_client() as client:
    with app.app_context():
        t = SavedTemplate.query.first()
        if t:
            res = client.post(f'/api/deploy_template/{t.id}?mode=deploy')
            print("Status:", res.status_code)
            print("Response:", res.text)
        else:
            print("No templates exist!")
