import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

in_func = False
for line in lines:
    if 'def recompute_route_metrics' in line:
        in_func = True
    if in_func:
        print(line, end='')
    if in_func and 'def ' in line and 'def recompute' not in line:
        break
