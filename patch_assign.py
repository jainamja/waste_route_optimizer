import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

new_endpoint = """@app.route('/api/assign_route', methods=['POST'])
@login_required
def assign_route():
    driver_id = request.json.get('driver_id')
    template_id = request.json.get('template_id')
    
    driver = User.query.get(driver_id)
    if not driver: return jsonify({'error': 'Driver not found'}), 404
    
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        API_KEY = "AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg"
        auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
        auth_res = requests.post(auth_url, json={"returnSecureToken": True})
        id_token = auth_res.json().get('idToken') if auth_res.status_code == 200 else None
    except:
        id_token = None
    
    if not template_id:
        driver.assigned_template_id = None
        Customer.query.filter_by(truck_id=driver.truck_id).delete()
        db.session.commit()
        if id_token:
            requests.delete(f"{firebase_url}/routes/route_{driver.truck_id}.json?auth={id_token}")
        recompute_route_metrics()
        return jsonify({'success': True})
        
    t = SavedTemplate.query.get(template_id)
    if not t: return jsonify({'error': 'Template not found'}), 404
    
    driver.assigned_template_id = template_id
    Customer.query.filter_by(truck_id=driver.truck_id).delete()
    
    import json
    cust_list = json.loads(t.customers_json or '[]')
    
    for c in cust_list:
        new_cust = Customer(
            id=c['id'], name=c['name'], phone=c.get('phone'), address=c.get('address'),
            location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
            status='PENDING', truck_id=driver.truck_id, stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
            customer_status=c.get('customer_status', 'ACTIVE')
        )
        db.session.add(new_cust)
        
    db.session.commit()
    
    if id_token:
        try:
            new_custs = Customer.query.filter_by(truck_id=driver.truck_id).all()
            if new_custs:
                route_key = f"route_{driver.truck_id}"
                stops_payload = {}
                for c in new_custs:
                    stops_payload[str(c.id)] = {
                        "name": c.name,
                        "address": c.address,
                        "phone": c.phone or '',
                        "lat": c.lat,
                        "lng": c.lng,
                        "sequence": c.stop_number,
                        "status": "PENDING",
                        "confirmation": c.confirmation,
                        "customer_status": getattr(c, 'customer_status', 'ACTIVE')
                    }
                requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops_payload})
                requests.put(f"{firebase_url}/trucks/{driver.truck_id}.json?auth={id_token}", json={"status": "offline"})
        except Exception as e:
            print("Firebase sync error assigning:", e)
            
    recompute_route_metrics()
    return jsonify({'success': True})

@app.route('/api/save_template',"""

text = text.replace("@app.route('/api/save_template',", new_endpoint)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
