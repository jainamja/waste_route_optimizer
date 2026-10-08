from waste_route_optimizer import app, db, Customer

with app.app_context():
    c = Customer.query.first()
    print("Found customer:", c.id, c.customer_status)
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        API_KEY = "AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg"
        auth_res = requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}", json={"returnSecureToken": True})
        if auth_res.status_code == 200:
            id_token = auth_res.json().get('idToken')
            payload = { "customer_status": "INACTIVE" }
            patch_url = f"{firebase_url}/routes/route_{c.truck_id}/stops/{c.id}.json?auth={id_token}"
            print("Patching to", patch_url)
            r = requests.patch(patch_url, json=payload)
            print("Response:", r.status_code, r.text)
    except Exception as e:
        print("Firebase error", e)
