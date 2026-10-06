import os
import re

filepath = 'waste_route_optimizer.py'
content = open(filepath, 'r', encoding='utf-8').read()

# 1. Update Customer Model
old_customer_model = """    lng = db.Column(db.Float)
    status = db.Column(db.String(50), default='PENDING')
    truck_id = db.Column(db.Integer)
    stop_number = db.Column(db.Integer)"""
new_customer_model = """    lng = db.Column(db.Float)
    status = db.Column(db.String(50), default='PENDING')
    truck_id = db.Column(db.Integer)
    stop_number = db.Column(db.Integer)
    confirmation = db.Column(db.String(20), default='NOT_CONFIRMED')"""
content = content.replace(old_customer_model, new_customer_model)

# 2. Update Migration
old_migration = """    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN name VARCHAR(100);'))
        db.session.commit()
    except:
        db.session.rollback()"""
new_migration = """    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN name VARCHAR(100);'))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN confirmation VARCHAR(20) DEFAULT 'NOT_CONFIRMED';"))
        db.session.commit()
    except:
        db.session.rollback()"""
content = content.replace(old_migration, new_migration)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS Step 1")
