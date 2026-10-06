import os
import re

filepath = 'waste_route_optimizer.py'
content = open(filepath, 'r', encoding='utf-8').read()

old_assign = """def assign_driver():
    data = request.json
    driver_id = data.get('driver_id')
    truck_id = data.get('truck_id')
    
    if not driver_id or not truck_id:
        return jsonify({'error': 'Missing fields'}), 400
        
    driver = User.query.get(driver_id)
    if not driver or driver.role != 'DRIVER':
        return jsonify({'error': 'Driver not found'}), 404
        
    # Remove this truck_id from any other driver to prevent duplicates
    User.query.filter_by(role='DRIVER', truck_id=truck_id).update({'truck_id': None})
    
    driver.truck_id = truck_id
    db.session.commit()
    
    return jsonify({'success': True})"""

new_assign = """def assign_driver():
    data = request.json
    driver_id = data.get('driver_id')
    truck_id = data.get('truck_id')
    confirmations = data.get('confirmations') # optional dict
    
    if not driver_id or not truck_id:
        return jsonify({'error': 'Missing fields'}), 400
        
    driver = User.query.get(driver_id)
    if not driver or driver.role != 'DRIVER':
        return jsonify({'error': 'Driver not found'}), 404
        
    # Remove this truck_id from any other driver to prevent duplicates
    User.query.filter_by(role='DRIVER', truck_id=truck_id).update({'truck_id': None})
    driver.truck_id = truck_id
    
    # Process confirmations if provided
    firebase_synced = True
    if confirmations is not None:
        customers_on_truck = Customer.query.filter_by(truck_id=truck_id).all()
        firebase_patch_data = {}
        
        for c in customers_on_truck:
            if c.id < 0: continue # Ignore depot rows
            
            c_val = confirmations.get(str(c.id))
            if c_val not in ['CONFIRMED', 'NOT_CONFIRMED']:
                c_val = 'NOT_CONFIRMED'
                
            c.confirmation = c_val
            firebase_patch_data[f"{c.id}/confirmation"] = c_val
            
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            API_KEY = "AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg"
            auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
            auth_res = requests.post(auth_url, json={"returnSecureToken": True})
            
            if auth_res.status_code == 200:
                id_token = auth_res.json().get('idToken')
                res = requests.patch(f"{firebase_url}/routes/route_{truck_id}/stops.json?auth={id_token}", json=firebase_patch_data)
                if res.status_code != 200:
                    firebase_synced = False
            else:
                firebase_synced = False
        except:
            firebase_synced = False
            
    db.session.commit()
    
    return jsonify({'success': True, 'firebase_synced': firebase_synced})"""

content = content.replace(old_assign, new_assign)
open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS Step 4")
