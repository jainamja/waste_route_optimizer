import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

in_data = False
for line in lines:
    if 'def get_data()' in line:
        in_data = True
    if in_data:
        print(line, end='')
    if in_data and 'return jsonify' in line:
        break
