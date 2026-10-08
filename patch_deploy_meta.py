import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_code = """    is_template_val = 'true' if mode == 'deploy' else 'false'
    db.session.add(Metadata(key='is_from_template', value=is_template_val))
        
    for c in cust_list:"""

new_code = """    is_template_val = 'true' if mode == 'deploy' else 'false'
    db.session.add(Metadata(key='is_from_template', value=is_template_val))
    if mode == 'deploy':
        db.session.add(Metadata(key='current_template_id', value=str(t.id)))
        db.session.add(Metadata(key='current_template_name', value=str(t.name)))
        
    for c in cust_list:"""

text = text.replace(old_code, new_code)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
