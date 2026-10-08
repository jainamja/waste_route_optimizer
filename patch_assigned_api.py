import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

new_ep = """@app.route('/api/assigned_routes', methods=['GET'])
@login_required
def get_assigned_routes():
    drivers = User.query.filter(User.assigned_template_id.isnot(None)).all()
    assigned_t_ids = list(set([d.assigned_template_id for d in drivers]))
    
    res = []
    for t_id in assigned_t_ids:
        t = SavedTemplate.query.get(t_id)
        if t:
            import json
            cust_list = json.loads(t.customers_json or '[]')
            res.append({
                'id': t.id,
                'name': t.name,
                'stops_count': len(cust_list),
                'truck_ids': [d.truck_id for d in drivers if d.assigned_template_id == t.id]
            })
    return jsonify({'success': True, 'assigned_routes': res})

@app.route('/api/delete_template/<int:t_id>', methods=['DELETE'])"""

text = text.replace("@app.route('/api/delete_template/<int:t_id>', methods=['DELETE'])", new_ep)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
