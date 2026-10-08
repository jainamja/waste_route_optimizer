import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_user = """    role = db.Column(db.String(20))
    truck_id = db.Column(db.Integer)
    name = db.Column(db.String(100))"""

new_user = """    role = db.Column(db.String(20))
    truck_id = db.Column(db.Integer)
    name = db.Column(db.String(100))
    assigned_template_id = db.Column(db.Integer, nullable=True)"""

text = text.replace(old_user, new_user)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
