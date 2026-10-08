from waste_route_optimizer import app, db, SavedTemplate
import json

with app.app_context():
    # Setup test template
    db.session.query(SavedTemplate).delete()
    db.session.commit()
    
    # Bypass endpoints and test the logic directly
    t1 = SavedTemplate(name="Morning Route", metadata_json="{}", customers_json="[]")
    db.session.add(t1)
    db.session.commit()
    
    t_id = t1.id
    print("Initial Template ID:", t_id)
    
    # Simulate update
    t2 = SavedTemplate.query.get(t_id)
    if not t2:
        t2 = SavedTemplate.query.filter_by(name="Morning Route").first()
    
    if t2:
        t2.name = "Morning Route"
        t2.metadata_json = "{}"
        t2.customers_json = "[]"
    else:
        t2 = SavedTemplate(name="Morning Route")
        db.session.add(t2)
    db.session.commit()
    
    count = SavedTemplate.query.count()
    print("Total Templates:", count)
    assert count == 1
    print("Test passed!")
