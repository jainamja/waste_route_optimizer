import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_save_commit = """    db.session.commit()
    
    return jsonify({'success': True})"""

new_save_commit = """    db.session.commit()
    
    # Auto-sync to any driver assigned to this template
    affected_drivers = User.query.filter_by(assigned_template_id=t.id).all()
    if affected_drivers:
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            API_KEY = "AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg"
            auth_res = requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}", json={"returnSecureToken": True})
            id_token = auth_res.json().get('idToken') if auth_res.status_code == 200 else None
        except:
            id_token = None
            
        for d in affected_drivers:
            # We skip wiping live if the edit is currently for this truck (already live)
            # Actually, to be safe, just wipe and reload from the newly saved template
            Customer.query.filter_by(truck_id=d.truck_id).delete()
            for c in cust_list:
                new_cust = Customer(
                    id=c['id'], name=c['name'], phone=c.get('phone'), address=c.get('address'),
                    location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
                    status=c.get('status', 'PENDING'), truck_id=d.truck_id, stop_number=c.get('stop_number'),
                    confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
                    customer_status=c.get('customer_status', 'ACTIVE')
                )
                db.session.add(new_cust)
            db.session.commit()
            
            if id_token:
                try:
                    new_custs = Customer.query.filter_by(truck_id=d.truck_id).all()
                    if new_custs:
                        route_key = f"route_{d.truck_id}"
                        stops_payload = {}
                        for c in new_custs:
                            stops_payload[str(c.id)] = {
                                "name": c.name,
                                "address": c.address,
                                "phone": c.phone or '',
                                "lat": c.lat,
                                "lng": c.lng,
                                "sequence": c.stop_number,
                                "status": c.status,
                                "confirmation": c.confirmation,
                                "customer_status": getattr(c, 'customer_status', 'ACTIVE')
                            }
                        requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops_payload})
                except Exception as e:
                    print("Firebase sync error on template save:", e)
        recompute_route_metrics()
    
    return jsonify({'success': True})"""

text = text.replace(old_save_commit, new_save_commit)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
