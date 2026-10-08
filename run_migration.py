from waste_route_optimizer import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE customer ADD COLUMN customer_status VARCHAR(20) DEFAULT 'ACTIVE';"))
        db.session.commit()
        print("Migrated successfully")
    except Exception as e:
        db.session.rollback()
        print(f"Error 1: {e}")
        
    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN customer_status VARCHAR(20) DEFAULT 'ACTIVE';"))
        db.session.commit()
        print("Migrated successfully 2")
    except Exception as e:
        db.session.rollback()
        print(f"Error 2: {e}")
