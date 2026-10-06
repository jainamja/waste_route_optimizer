import os

filepath = 'waste_route_optimizer.py'
content = open(filepath, 'r', encoding='utf-8').read()

old_assign = """def assign_driver():
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
    driver.truck_id = truck_id"""

new_assign = """def assign_driver():
    data = request.json
    driver_id = data.get('driver_id')
    truck_id = data.get('truck_id')
    confirmations = data.get('confirmations') # optional dict
    
    if not truck_id:
        return jsonify({'error': 'Missing truck_id'}), 400
        
    if driver_id:
        driver = User.query.get(driver_id)
        if not driver or driver.role != 'DRIVER':
            return jsonify({'error': 'Driver not found'}), 404
            
        # Remove this truck_id from any other driver to prevent duplicates
        User.query.filter_by(role='DRIVER', truck_id=truck_id).update({'truck_id': None})
        driver.truck_id = truck_id"""
        
content = content.replace(old_assign, new_assign)
open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS")
