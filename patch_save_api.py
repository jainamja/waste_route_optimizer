import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_save = """@app.route('/api/save_template', methods=['POST'])
@login_required
def save_template():
    name = request.json.get('name')
    if not name: return jsonify({'error': 'Name is required'}), 400
    
    import json
    
    # Dump Metadata
    meta_rows = Metadata.query.all()
    meta_dict = {m.key: m.value for m in meta_rows}
    
    # Dump Customers
    cust_rows = Customer.query.all()
    cust_list = [{
        'id': c.id, 'name': c.name, 'phone': c.phone, 'address': c.address,
        'location_url': c.location_url, 'lat': c.lat, 'lng': c.lng,
        'status': c.status, 'truck_id': c.truck_id, 'stop_number': c.stop_number,
        'confirmation': c.confirmation if c.confirmation else 'NOT_CONFIRMED',
        'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE'
    } for c in cust_rows]
    
    t = SavedTemplate.query.filter_by(name=name).first()
    if t:
        t.metadata_json = json.dumps(meta_dict)
        t.customers_json = json.dumps(cust_list)
        t.created_at = db.func.now()
    else:
        t = SavedTemplate(
            name=name,
            metadata_json=json.dumps(meta_dict),
            customers_json=json.dumps(cust_list)
        )
        db.session.add(t)
    db.session.commit()
    
    return jsonify({'success': True})"""

new_save = """@app.route('/api/save_template', methods=['POST'])
@login_required
def save_template():
    name = request.json.get('name')
    t_id = request.json.get('id')
    if not name: return jsonify({'error': 'Name is required'}), 400
    
    import json
    
    # Dump Metadata
    meta_rows = Metadata.query.all()
    meta_dict = {m.key: m.value for m in meta_rows}
    
    # Dump Customers
    cust_rows = Customer.query.all()
    cust_list = [{
        'id': c.id, 'name': c.name, 'phone': c.phone, 'address': c.address,
        'location_url': c.location_url, 'lat': c.lat, 'lng': c.lng,
        'status': c.status, 'truck_id': c.truck_id, 'stop_number': c.stop_number,
        'confirmation': c.confirmation if c.confirmation else 'NOT_CONFIRMED',
        'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE'
    } for c in cust_rows]
    
    t = None
    if t_id:
        t = SavedTemplate.query.get(t_id)
    if not t:
        t = SavedTemplate.query.filter_by(name=name).first()
        
    if t:
        t.name = name
        t.metadata_json = json.dumps(meta_dict)
        t.customers_json = json.dumps(cust_list)
        t.created_at = db.func.now()
    else:
        t = SavedTemplate(
            name=name,
            metadata_json=json.dumps(meta_dict),
            customers_json=json.dumps(cust_list)
        )
        db.session.add(t)
    db.session.commit()
    
    return jsonify({'success': True})"""

text = text.replace(old_save, new_save)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
