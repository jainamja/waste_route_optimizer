import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_mig = """    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN name VARCHAR(100);'))
        db.session.commit()
    except:
        db.session.rollback()"""

new_mig = """    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN name VARCHAR(100);'))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN assigned_template_id INTEGER;'))
        db.session.commit()
    except:
        db.session.rollback()"""

text = text.replace(old_mig, new_mig)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
