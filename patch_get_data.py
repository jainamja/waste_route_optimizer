import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_get_data = """    drivers = User.query.filter_by(role='DRIVER').all()
    drivers_data = []
    for d in drivers:
        drivers_data.append({
            'id': d.id,
            'username': d.username,
            'name': d.name,
            'truck_id': d.truck_id
        })"""

new_get_data = """    drivers = User.query.filter_by(role='DRIVER').all()
    drivers_data = []
    for d in drivers:
        assigned_name = "No Route Assigned"
        if getattr(d, 'assigned_template_id', None):
            t = SavedTemplate.query.get(d.assigned_template_id)
            if t: assigned_name = t.name
            
        drivers_data.append({
            'id': d.id,
            'username': d.username,
            'name': d.name,
            'truck_id': d.truck_id,
            'assigned_template_id': getattr(d, 'assigned_template_id', None),
            'assigned_template_name': assigned_name
        })"""

text = text.replace(old_get_data, new_get_data)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
