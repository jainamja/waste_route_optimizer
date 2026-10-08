from waste_route_optimizer import app, db, Customer

with app.app_context():
    c = Customer.query.first()
    print("Found customer:", c.id)
    c.customer_status = "INACTIVE"
    try:
        db.session.commit()
        print("Commit success!")
    except Exception as e:
        print("Commit error:", e)
