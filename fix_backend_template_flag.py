import os

filepath = 'waste_route_optimizer.py'
content = open(filepath, 'r', encoding='utf-8').read()

# 1. Update upload() to set is_from_template = false
old_upload = """    m4 = Metadata(key='route_distances', value=json.dumps(active_route_distances))
    m_tokens = Metadata(key='driver_tokens', value=json.dumps(driver_tokens))
    db.session.add_all([m1, m2, m3, m4, m_tokens])"""
new_upload = """    m4 = Metadata(key='route_distances', value=json.dumps(active_route_distances))
    m_tokens = Metadata(key='driver_tokens', value=json.dumps(driver_tokens))
    m_template = Metadata(key='is_from_template', value='false')
    db.session.add_all([m1, m2, m3, m4, m_tokens, m_template])"""
content = content.replace(old_upload, new_upload)

# 2. Update deploy_template() to accept mode and set is_from_template
old_deploy = """def deploy_template(t_id):
    t = SavedTemplate.query.get(t_id)"""
new_deploy = """def deploy_template(t_id):
    mode = request.args.get('mode', 'deploy')
    t = SavedTemplate.query.get(t_id)"""
content = content.replace(old_deploy, new_deploy)

old_deploy_meta = """    for k, v in meta_dict.items():
        db.session.add(Metadata(key=k, value=v))"""
new_deploy_meta = """    for k, v in meta_dict.items():
        if k != 'is_from_template':
            db.session.add(Metadata(key=k, value=v))
            
    is_template_val = 'true' if mode == 'deploy' else 'false'
    db.session.add(Metadata(key='is_from_template', value=is_template_val))"""
content = content.replace(old_deploy_meta, new_deploy_meta)

# 3. Return is_from_template in /api/data
old_get_data = """    return jsonify({
        'customers': customers,
        'routes': routes,
        'route_times': route_times,
        'route_distances': route_distances,
        'start_coords': start_coords,
        'end_coords': end_coords,
        'driver_tokens': driver_tokens,
        'drivers': drivers_data
    })"""
new_get_data = """    return jsonify({
        'customers': customers,
        'routes': routes,
        'route_times': route_times,
        'route_distances': route_distances,
        'start_coords': start_coords,
        'end_coords': end_coords,
        'driver_tokens': driver_tokens,
        'drivers': drivers_data,
        'is_from_template': metadata.get('is_from_template') == 'true'
    })"""
content = content.replace(old_get_data, new_get_data)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS")
