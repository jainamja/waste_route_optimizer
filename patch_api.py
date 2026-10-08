import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_func = """    # Check if assigned to an active route
    if c.truck_id and c.stop_number:
        id_token = get_firebase_token()
        if id_token:
            payload = { "customer_status": status }
            requests.patch(f"{firebase_url}/routes/route_{c.truck_id}/stops/{c.id}.json?auth={id_token}", json=payload)"""

new_func = """    # Check if assigned to an active route
    if c.truck_id and c.stop_number:
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            API_KEY = "AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg"
            auth_res = requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}", json={"returnSecureToken": True})
            if auth_res.status_code == 200:
                id_token = auth_res.json().get('idToken')
                payload = { "customer_status": status }
                requests.patch(f"{firebase_url}/routes/route_{c.truck_id}/stops/{c.id}.json?auth={id_token}", json=payload)
        except Exception as e:
            print("Firebase sync error in update_customer_status:", e)"""

text = text.replace(old_func, new_func)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
