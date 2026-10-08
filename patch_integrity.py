import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_loop = """      for k, v in meta_dict.items():
          if k != 'is_from_template':
              db.session.add(Metadata(key=k, value=v))
              
      is_template_val = 'true' if mode == 'deploy' else 'false'
      db.session.add(Metadata(key='is_from_template', value=is_template_val))
      db.session.add(Metadata(key='current_template_id', value=str(t.id)))
      db.session.add(Metadata(key='current_template_name', value=str(t.name)))"""

new_loop = """      for k, v in meta_dict.items():
          if k not in ['is_from_template', 'current_template_id', 'current_template_name']:
              db.session.add(Metadata(key=k, value=v))
              
      is_template_val = 'true' if mode == 'deploy' else 'false'
      db.session.add(Metadata(key='is_from_template', value=is_template_val))
      db.session.add(Metadata(key='current_template_id', value=str(t.id)))
      db.session.add(Metadata(key='current_template_name', value=str(t.name)))"""

text = text.replace(old_loop, new_loop)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
