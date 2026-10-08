import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_json = """    for r in customers_db:
        customers.append({
            'id': r.id, 'name': r.name, 'phone': r.phone, 'address': r.address,
            'location_url': r.location_url, 'lat': r.lat, 'lng': r.lng,
            'status': r.status, 'truck': r.truck_id, 'stop_number': r.stop_number,
            'confirmation': r.confirmation if r.confirmation else 'NOT_CONFIRMED'
        })"""

new_json = """    for r in customers_db:
        customers.append({
            'id': r.id, 'name': r.name, 'phone': r.phone, 'address': r.address,
            'location_url': r.location_url, 'lat': r.lat, 'lng': r.lng,
            'status': r.status, 'truck': r.truck_id, 'stop_number': r.stop_number,
            'confirmation': r.confirmation if r.confirmation else 'NOT_CONFIRMED',
            'customer_status': getattr(r, 'customer_status', 'ACTIVE') or 'ACTIVE'
        })"""

text = text.replace(old_json, new_json)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done!")
