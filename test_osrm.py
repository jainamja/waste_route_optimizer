from waste_route_optimizer import read_data_file
from aco_vrp import ACO_VRP
import requests

c = read_data_file('uploads/Bintix GGPL - Tuesday Dry Waste collection.docx')
aco = ACO_VRP((23.0225, 72.5714), (23.277034, 72.4335751857), c, num_trucks=3, num_iterations=5, num_ants=5)
routes, dist = aco.run()

for i, route in enumerate(routes):
    coords = [(23.0225, 72.5714)]
    for cid in route:
        cust = next(cust for cust in c if cust['id'] == cid)
        coords.append((cust['lat'], cust['lng']))
    coords.append((23.277034, 72.4335751857))
    
    coordsString = ';'.join([f'{lng},{lat}' for lat, lng in coords])
    url = f'https://router.project-osrm.org/route/v1/driving/{coordsString}?overview=full'
    res = requests.get(url)
    data = res.json()
    print(f'Route {i}: {res.status_code}, {data.get("code")}')
    if data.get("code") != "Ok":
        print(data.get("message"))
