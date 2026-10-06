import os

filepath = 'waste_route_optimizer.py'
content = open(filepath, 'r', encoding='utf-8').read()

old_logic = """    t = SavedTemplate(
        name=name,
        metadata_json=json.dumps(meta_dict),
        customers_json=json.dumps(cust_list)
    )
    db.session.add(t)"""
    
new_logic = """    t = SavedTemplate.query.filter_by(name=name).first()
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
        db.session.add(t)"""
        
content = content.replace(old_logic, new_logic)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS")
