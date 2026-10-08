import io
import re

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Add column to model
text = text.replace(
    "confirmation = db.Column(db.String(20), default='NOT_CONFIRMED')",
    "confirmation = db.Column(db.String(20), default='NOT_CONFIRMED')\n    customer_status = db.Column(db.String(20), default='ACTIVE')"
)

# Add migration
migration = """    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN confirmation VARCHAR(20) DEFAULT 'NOT_CONFIRMED';"))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN customer_status VARCHAR(20) DEFAULT 'ACTIVE';"))
        db.session.commit()
    except:
        db.session.rollback()"""

text = text.replace(
'''    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN confirmation VARCHAR(20) DEFAULT 'NOT_CONFIRMED';"))
        db.session.commit()
    except:
        db.session.rollback()''',
    migration
)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done!")
