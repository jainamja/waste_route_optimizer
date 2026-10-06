import os
import re

filepath = 'waste_route_optimizer.py'
content = open(filepath, 'r', encoding='utf-8').read()

# 1. Update /upload Customer constructor
old_upload = """        new_cust = Customer(
            id=c['id'], name=c['name'], phone=c['phone'], address=c['address'],
            location_url=c['location_url'], lat=c['lat'], lng=c['lng'],
            status=c.get('status', 'PENDING'), truck_id=c.get('truck'), stop_number=c.get('stop_number')
        )"""
new_upload = """        new_cust = Customer(
            id=c['id'], name=c['name'], phone=c['phone'], address=c['address'],
            location_url=c['location_url'], lat=c['lat'], lng=c['lng'],
            status=c.get('status', 'PENDING'), truck_id=c.get('truck'), stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED')
        )"""
content = content.replace(old_upload, new_upload)

# 2. Update /api/add_stop target constructor
old_add1 = """            new_cust = Customer(
                id=new_id, name=name, phone=phone, address=address,
                location_url=location_url, lat=lat, lng=lng,
                status='PENDING', truck_id=target_truck_id, stop_number=target_sequence + 1
            )"""
new_add1 = """            new_cust = Customer(
                id=new_id, name=name, phone=phone, address=address,
                location_url=location_url, lat=lat, lng=lng,
                status='PENDING', truck_id=target_truck_id, stop_number=target_sequence + 1,
                confirmation='NOT_CONFIRMED'
            )"""
content = content.replace(old_add1, new_add1)

# 3. Update /api/add_stop auto constructor
old_add2 = """            new_cust = Customer(
                id=new_id, name=name, phone=phone, address=address,
                location_url=location_url, lat=lat, lng=lng, status='PENDING'
            )"""
new_add2 = """            new_cust = Customer(
                id=new_id, name=name, phone=phone, address=address,
                location_url=location_url, lat=lat, lng=lng, status='PENDING',
                confirmation='NOT_CONFIRMED'
            )"""
content = content.replace(old_add2, new_add2)

# 4. Update get_data() dict
old_get_data = """        customers.append({
            'id': r.id, 'name': r.name, 'phone': r.phone, 'address': r.address,
            'location_url': r.location_url, 'lat': r.lat, 'lng': r.lng,
            'status': r.status, 'truck': r.truck_id, 'stop_number': r.stop_number
        })"""
new_get_data = """        customers.append({
            'id': r.id, 'name': r.name, 'phone': r.phone, 'address': r.address,
            'location_url': r.location_url, 'lat': r.lat, 'lng': r.lng,
            'status': r.status, 'truck': r.truck_id, 'stop_number': r.stop_number,
            'confirmation': r.confirmation if r.confirmation else 'NOT_CONFIRMED'
        })"""
content = content.replace(old_get_data, new_get_data)

# 5. Update save_template() dict
old_save_t = """    cust_list = [{
        'id': c.id, 'name': c.name, 'phone': c.phone, 'address': c.address,
        'location_url': c.location_url, 'lat': c.lat, 'lng': c.lng,
        'status': c.status, 'truck_id': c.truck_id, 'stop_number': c.stop_number
    } for c in cust_rows]"""
new_save_t = """    cust_list = [{
        'id': c.id, 'name': c.name, 'phone': c.phone, 'address': c.address,
        'location_url': c.location_url, 'lat': c.lat, 'lng': c.lng,
        'status': c.status, 'truck_id': c.truck_id, 'stop_number': c.stop_number,
        'confirmation': c.confirmation if c.confirmation else 'NOT_CONFIRMED'
    } for c in cust_rows]"""
content = content.replace(old_save_t, new_save_t)

# 6. Update deploy_template() Customer constructor
old_deploy_t = """        new_cust = Customer(
            id=c['id'], name=c['name'], phone=c['phone'], address=c['address'],
            location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
            status='PENDING', truck_id=c.get('truck_id'), stop_number=c.get('stop_number')
        )"""
new_deploy_t = """        new_cust = Customer(
            id=c['id'], name=c['name'], phone=c['phone'], address=c['address'],
            location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
            status='PENDING', truck_id=c.get('truck_id'), stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED')
        )"""
content = content.replace(old_deploy_t, new_deploy_t)

# 7. Update download_excel()
old_download = """    headers = ["Sr No", "Name", "Phone", "Address", "Status", "Truck ID", "Stop Number"]
    
    def generate():
        yield ','.join(headers) + '\\n'
        for c in customers:
            yield f"{c.id},\"{c.name}\",\"{c.phone}\",\"{c.address}\",{c.status},{c.truck_id},{c.stop_number}\\n" """
new_download = """    headers = ["Sr No", "Name", "Phone", "Address", "Status", "Truck ID", "Stop Number", "Confirmation"]
    
    def generate():
        yield ','.join(headers) + '\\n'
        for c in customers:
            conf = c.confirmation if c.confirmation else 'NOT_CONFIRMED'
            yield f"{c.id},\"{c.name}\",\"{c.phone}\",\"{c.address}\",{c.status},{c.truck_id},{c.stop_number},{conf}\\n" """
content = content.replace(old_download, new_download)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS Step 2")
