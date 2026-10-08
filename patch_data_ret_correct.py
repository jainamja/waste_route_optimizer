import io
import re

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_return = """    return jsonify({
        'customers': customers,
        'routes': routes,
        'route_times': route_times,
        'route_distances': route_distances,
        'start_coords': start_coords,
        'end_coords': end_coords,
        'driver_tokens': driver_tokens,
        'drivers': drivers_data,
        'is_from_template': metadata.get('is_from_template') == 'true'
    })"""

new_return = """    return jsonify({
        'customers': customers,
        'routes': routes,
        'route_times': route_times,
        'route_distances': route_distances,
        'start_coords': start_coords,
        'end_coords': end_coords,
        'driver_tokens': driver_tokens,
        'drivers': drivers_data,
        'is_from_template': metadata.get('is_from_template') == 'true',
        'current_template_id': metadata.get('current_template_id'),
        'current_template_name': metadata.get('current_template_name')
    })"""

if old_return in text:
    text = text.replace(old_return, new_return)
else:
    print("FAILED TO MATCH")
    exit(1)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
