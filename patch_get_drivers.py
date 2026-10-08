import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_func = """@app.route('/api/drivers', methods=['GET'])
@login_required
def get_drivers():
    drivers = User.query.filter_by(role='DRIVER').all()
    drivers_data = []
    for d in drivers:
        drivers_data.append({
            'id': d.id,
            'username': d.username,
            'name': d.name,
            'truck_id': d.truck_id,
            'password_hash': 'redacted'
        })
    return jsonify({'drivers': drivers_data})"""

new_func = """@app.route('/api/drivers', methods=['GET'])
@login_required
def get_drivers():
    drivers = User.query.filter_by(role='DRIVER').all()
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
            'password_hash': 'redacted',
            'assigned_template_id': getattr(d, 'assigned_template_id', None),
            'assigned_template_name': assigned_name
        })
    return jsonify({'drivers': drivers_data})"""

text = text.replace(old_func, new_func)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
