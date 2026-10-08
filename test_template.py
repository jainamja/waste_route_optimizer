from waste_route_optimizer import app, db, SavedTemplate, Customer, Metadata
import json

with app.test_client() as client:
    with app.app_context():
        # Setup test template
        db.session.query(SavedTemplate).delete()
        db.session.commit()
        
        # 1. Create a route
        res = client.post('/api/save_template', json={'name': 'Morning Route'})
        assert res.json['success'] == True
        
        t = SavedTemplate.query.first()
        t_id = t.id
        print("Created template ID:", t_id)
        
        # 2. Deploy it (Simulates clicking Edit)
        res = client.post(f'/api/deploy_template/{t_id}?mode=deploy')
        assert res.json['success'] == True
        
        # 3. Fetch data to ensure it has template metadata
        res = client.get('/api/data')
        data = res.json
        assert data['is_from_template'] == True
        assert str(data['current_template_id']) == str(t_id)
        assert data['current_template_name'] == 'Morning Route'
        
        # 4. Save it again (Simulates clicking Save)
        res = client.post('/api/save_template', json={'id': t_id, 'name': 'Morning Route'})
        assert res.json['success'] == True
        
        # 5. Verify there is only one template
        templates = SavedTemplate.query.all()
        assert len(templates) == 1
        assert templates[0].id == t_id
        print("Test passed! Only ONE template exists, ID retained.")
