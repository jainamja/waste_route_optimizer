import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_commit = """        db.session.add(new_cust)
        
    db.session.commit()
    
    # Sync with Firebase immediately"""

new_commit = """        db.session.add(new_cust)
        
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Database error during deploy: {str(e)}'}), 500
    
    # Sync with Firebase immediately"""

if old_commit in text:
    text = text.replace(old_commit, new_commit)
    with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    print("Done")
else:
    print("Failed to find block!")
