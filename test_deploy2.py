from waste_route_optimizer import app, db, SavedTemplate, Metadata, Customer
import json

with app.app_context():
    # create dummy 4
    t = SavedTemplate.query.get(4)
    if not t:
        t = SavedTemplate(id=4, name="Test4", metadata_json="{}", customers_json="[]")
        db.session.add(t)
        db.session.commit()
    
    try:
        t_id = 4
        mode = 'deploy'
        t = SavedTemplate.query.get(t_id)
        
        meta_dict = json.loads(t.metadata_json or '{}')
        cust_list = json.loads(t.customers_json or '[]')
        
        Customer.query.delete()
        Metadata.query.delete()
        
        for k, v in meta_dict.items():
            if k != 'is_from_template':
                db.session.add(Metadata(key=k, value=v))
                
        is_template_val = 'true' if mode == 'deploy' else 'false'
        db.session.add(Metadata(key='is_from_template', value=is_template_val))
        db.session.add(Metadata(key='current_template_id', value=str(t.id)))
        db.session.add(Metadata(key='current_template_name', value=str(t.name)))
            
        for c in cust_list:
            new_cust = Customer(
                id=c['id'], name=c['name'], phone=c['phone'], address=c['address'],
                location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
                status='PENDING', truck_id=c.get('truck_id'), stop_number=c.get('stop_number'),
                confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
                customer_status=c.get('customer_status', 'ACTIVE')
            )
            db.session.add(new_cust)
            
        db.session.commit()
        print("Success without error!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Error:", e)
