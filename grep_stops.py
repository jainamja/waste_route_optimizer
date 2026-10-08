import io

with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'stops' in line:
        print(f"[{i+1}] {line.strip()}")
