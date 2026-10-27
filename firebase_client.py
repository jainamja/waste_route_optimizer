import os
import time
import requests

class FirebaseClient:
    def __init__(self, api_key=None, db_url=None):
        self.api_key = api_key or os.getenv("FIREBASE_API_KEY", "AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg")
        self.db_url = (db_url or os.getenv("FIREBASE_DB_URL", "https://wasteroutelive-default-rtdb.firebaseio.com")).rstrip('/')
        self._token_cache = {"token": None, "expires": 0}

    def get_token(self):
        """
        Caches the anonymous idToken and refreshes it only when expired
        instead of calling signUp on every request.
        """
        now = time.time()
        if self._token_cache["token"] and now < self._token_cache["expires"]:
            return self._token_cache["token"]

        auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={self.api_key}"
        try:
            auth_res = requests.post(auth_url, json={"returnSecureToken": True}, timeout=10)
            if auth_res.status_code == 200:
                token_data = auth_res.json()
                expires_in = int(token_data.get('expiresIn', 3600))
                self._token_cache["token"] = token_data.get('idToken')
                # Refresh 10 minutes before actual expiration
                self._token_cache["expires"] = now + max(60, expires_in - 600)
                return self._token_cache["token"]
            else:
                print(f"[FirebaseClient] Auth failed ({auth_res.status_code}): {auth_res.text}")
        except Exception as e:
            print(f"[FirebaseClient] Auth exception: {e}")
        return None

    def get_trucks(self):
        token = self.get_token()
        if not token:
            return {}
        try:
            res = requests.get(f"{self.db_url}/trucks.json?auth={token}", timeout=8)
            if res.status_code == 200:
                return res.json() or {}
        except Exception as e:
            print(f"[FirebaseClient] get_trucks error: {e}")
        return {}

    def get_routes(self):
        token = self.get_token()
        if not token:
            return {}
        try:
            res = requests.get(f"{self.db_url}/routes.json?auth={token}", timeout=8)
            if res.status_code == 200:
                return res.json() or {}
        except Exception as e:
            print(f"[FirebaseClient] get_routes error: {e}")
        return {}

    def set_route_stops(self, truck_id, stops):
        token = self.get_token()
        if not token:
            return False
        route_key = f"route_{truck_id}" if not str(truck_id).startswith("route_") else str(truck_id)
        try:
            res = requests.put(f"{self.db_url}/routes/{route_key}.json?auth={token}", json={"stops": stops}, timeout=8)
            return res.status_code == 200
        except Exception as e:
            print(f"[FirebaseClient] set_route_stops error: {e}")
            return False

    def update_route_stops_only(self, truck_id, stops):
        token = self.get_token()
        if not token:
            return False
        route_key = f"route_{truck_id}" if not str(truck_id).startswith("route_") else str(truck_id)
        try:
            res = requests.put(f"{self.db_url}/routes/{route_key}/stops.json?auth={token}", json=stops, timeout=8)
            return res.status_code == 200
        except Exception as e:
            print(f"[FirebaseClient] update_route_stops_only error: {e}")
            return False

    def delete_route(self, truck_id):
        token = self.get_token()
        if not token:
            return False
        route_key = f"route_{truck_id}" if not str(truck_id).startswith("route_") else str(truck_id)
        try:
            res = requests.delete(f"{self.db_url}/routes/{route_key}.json?auth={token}", timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"[FirebaseClient] delete_route error: {e}")
            return False

    def patch_truck(self, truck_id, data):
        token = self.get_token()
        if not token:
            return False
        try:
            res = requests.patch(f"{self.db_url}/trucks/{truck_id}.json?auth={token}", json=data, timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"[FirebaseClient] patch_truck error: {e}")
            return False

    def put_truck(self, truck_id, data):
        token = self.get_token()
        if not token:
            return False
        try:
            res = requests.put(f"{self.db_url}/trucks/{truck_id}.json?auth={token}", json=data, timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"[FirebaseClient] put_truck error: {e}")
            return False

    def delete_truck(self, truck_id):
        token = self.get_token()
        if not token:
            return False
        try:
            res = requests.delete(f"{self.db_url}/trucks/{truck_id}.json?auth={token}", timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"[FirebaseClient] delete_truck error: {e}")
            return False

    def mark_stop_status(self, truck_id, stop_id, status="COMPLETED"):
        token = self.get_token()
        if not token or not truck_id or not stop_id:
            return False
        route_key = f"route_{truck_id}" if not str(truck_id).startswith("route_") else str(truck_id)
        try:
            res = requests.patch(f"{self.db_url}/routes/{route_key}/stops/{stop_id}.json?auth={token}", json={"status": status}, timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"[FirebaseClient] mark_stop_status error: {e}")
            return False

    def delete_driver_location(self, driver_id):
        token = self.get_token()
        if not token or not driver_id:
            return False
        try:
            res = requests.delete(f"{self.db_url}/driver_locations/{driver_id}.json?auth={token}", timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"[FirebaseClient] delete_driver_location error: {e}")
            return False

# Shared singleton instance
firebase_client = FirebaseClient()

def get_firebase_token():
    """
    Module-level helper that delegates to the shared FirebaseClient token cache.
    """
    return firebase_client.get_token()
