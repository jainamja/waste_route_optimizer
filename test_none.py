import requests

s = requests.Session()
s.post("http://127.0.0.1:5000/login", data={'username': 'admin', 'password': 'admin'})

# Let's hit a script endpoint to manually set all truck_ids to None
script = """
import requests
s = requests.Session()
s.post('http://127.0.0.1:5000/login', data={'username':'admin','password':'admin'})
"""
