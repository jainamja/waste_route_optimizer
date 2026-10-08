from waste_route_optimizer import app, db, User
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN assigned_template_id INTEGER;'))
        db.session.commit()
        print("Column added")
    except Exception as e:
        db.session.rollback()
        print("Error or already exists:", e)
