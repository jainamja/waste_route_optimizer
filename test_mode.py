from waste_route_optimizer import app, db, SavedTemplate
import json

with app.test_client() as client:
    with app.app_context():
        # Clean db
        db.session.query(SavedTemplate).delete()
        db.session.commit()
        
        # 1. Create a route
        client.post('/api/save_template', json={'name': 'Morning Route'})
        
        t = SavedTemplate.query.first()
        print("Template ID:", t.id)
        
        # 2. Deploy it in Edit mode
        res = client.post(f'/api/deploy_template/{t.id}?mode=edit')
        print("Deploy Mode Edit Response:", res.json)
        
        # 3. Fetch data
        res = client.get('/api/data')
        data = res.json
        print("is_from_template:", data.get('is_from_template'))
        print("current_template_id:", data.get('current_template_id'))
        print("current_template_name:", data.get('current_template_name'))
