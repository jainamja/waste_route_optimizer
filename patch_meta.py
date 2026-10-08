import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_deploy = """    is_template_val = 'true' if mode == 'deploy' else 'false'
    db.session.add(Metadata(key='is_from_template', value=is_template_val))
    if mode == 'deploy':
        db.session.add(Metadata(key='current_template_id', value=str(t.id)))
        db.session.add(Metadata(key='current_template_name', value=str(t.name)))"""

new_deploy = """    is_template_val = 'true' if mode == 'deploy' else 'false'
    db.session.add(Metadata(key='is_from_template', value=is_template_val))
    db.session.add(Metadata(key='current_template_id', value=str(t.id)))
    db.session.add(Metadata(key='current_template_name', value=str(t.name)))"""

text = text.replace(old_deploy, new_deploy)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
