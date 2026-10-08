import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "if k != 'is_from_template':" in line:
        new_lines.append("        if k not in ['is_from_template', 'current_template_id', 'current_template_name']:\n")
    else:
        new_lines.append(line)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    for line in new_lines:
        f.write(line)
print("Done")
