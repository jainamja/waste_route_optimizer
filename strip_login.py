
with open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if 'flash(\'Registration successful!' in line:
        skip = True
    if skip and 'return render_template(\'register.html\')' in line:
        skip = False
        continue
    
    if not skip:
        new_lines.append(line)

with open('waste_route_optimizer.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

