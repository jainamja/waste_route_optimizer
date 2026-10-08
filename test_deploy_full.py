from waste_route_optimizer import app, db, SavedTemplate, Metadata, Customer, recompute_route_metrics
import json

with app.app_context():
    # Setup test environment
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
        
        # Sync with Firebase immediately
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            API_KEY = "AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg"
            auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
            auth_res = requests.post(auth_url, json={"returnSecureToken": True})
            
            if auth_res.status_code == 200:
                id_token = auth_res.json().get('idToken')
                
                requests.delete(f"{firebase_url}/routes.json?auth={id_token}")
                
                routes_payload = {}
                for c in cust_list:
                    tid = c.get('truck_id')
                    if tid:
                        route_key = f"route_{tid}"
                        if route_key not in routes_payload: routes_payload[route_key] = {}
                        
                        routes_payload[route_key][str(c['id'])] = {
                            "name": c['name'],
                            "address": c['address'],
                            "phone": c.get('phone', ''),
                            "lat": c['lat'],
                            "lng": c['lng'],
                            "sequence": c.get('stop_number'),
                            "status": "PENDING",
                            "confirmation": c.get("confirmation", "NOT_CONFIRMED"),
                            "customer_status": c.get("customer_status", "ACTIVE")
                        }
                        
                for route_key, stops in routes_payload.items():
                    requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops})
                    tid = route_key.split('_')[1]
                    requests.put(f"{firebase_url}/trucks/{tid}.json?auth={id_token}", json={"status": "offline"})
        except Exception as e:
            print("Deploy Firebase error:", e)
            
        recompute_route_metrics()
        print("Success without error!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Error:", e)
