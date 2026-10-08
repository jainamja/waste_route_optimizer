import io
import re

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_func = """      for c in cust_list:
          new_cust = Customer(
              id=c['id'], name=c['name'], phone=c['phone'], address=c['address'],
              location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
              status='PENDING', truck_id=c.get('truck_id'), stop_number=c.get('stop_number'),
              confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
              customer_status=c.get('customer_status', 'ACTIVE')
          )
          db.session.add(new_cust)
          
      db.session.commit()
      
      # Sync with Firebase immediately"""

new_func = """      for c in cust_list:
          new_cust = Customer(
              id=c['id'], name=c['name'], phone=c['phone'], address=c['address'],
              location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
              status='PENDING', truck_id=c.get('truck_id'), stop_number=c.get('stop_number'),
              confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
              customer_status=c.get('customer_status', 'ACTIVE')
          )
          db.session.add(new_cust)
          
      try:
          db.session.commit()
      except Exception as e:
          db.session.rollback()
          import traceback
          traceback.print_exc()
          return jsonify({'error': f'Database error during deploy: {str(e)}'}), 500
      
      # Sync with Firebase immediately"""

text = text.replace(old_func, new_func)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
