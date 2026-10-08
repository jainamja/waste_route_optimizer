import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_deploy = """            status='PENDING', truck_id=c.get('truck_id'), stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED')
        )"""

new_deploy = """            status='PENDING', truck_id=c.get('truck_id'), stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
            customer_status=c.get('customer_status', 'ACTIVE')
        )"""

text = text.replace(old_deploy, new_deploy)

old_upload = """                status='PENDING',
                confirmation=c.get('confirmation', 'NOT_CONFIRMED')
            )
            db.session.add(new_cust)"""

new_upload = """                status='PENDING',
                confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
                customer_status=c.get('customer_status', 'ACTIVE')
            )
            db.session.add(new_cust)"""

text = text.replace(old_upload, new_upload)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done!")
