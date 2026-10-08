from waste_route_optimizer import app, db, SavedTemplate, Metadata
import json

with app.app_context():
    # Simulate deploy_template(mode='edit')
    db.session.query(Metadata).delete()
    db.session.commit()
    
    t = SavedTemplate(name="Test", metadata_json="{}", customers_json="[]")
    db.session.add(t)
    db.session.commit()
    
    # Inside deploy_template
    is_template_val = 'false'
    db.session.add(Metadata(key='is_from_template', value=is_template_val))
    db.session.add(Metadata(key='current_template_id', value=str(t.id)))
    db.session.add(Metadata(key='current_template_name', value=str(t.name)))
    db.session.commit()
    
    # Inside get_data
    metadata_rows = Metadata.query.all()
    metadata = {row.key: row.value for row in metadata_rows}
    print("Metadata:", metadata)
    print("is_from_template (boolean):", metadata.get('is_from_template') == 'true')
    print("current_template_id:", metadata.get('current_template_id'))
    print("current_template_name:", metadata.get('current_template_name'))
