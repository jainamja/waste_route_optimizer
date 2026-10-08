import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'return jsonify({' in line and 'metadata' in lines[i-50:i+10]:
        start = i
        while '})' not in lines[start] and start < i+20:
            print(lines[start], end='')
            start += 1
        print(lines[start], end='')
