import io
import re

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_func = """    c.customer_status = status
    db.session.commit()
    
    # Check if assigned to an active route"""

new_func = """    try:
        c.customer_status = status
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'DB Error: {str(e)}'}), 500
        
    # Check if assigned to an active route"""

text = text.replace(old_func, new_func)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
