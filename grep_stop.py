import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'Stop ' in line:
        print(f"[{i+1}] {line.strip()}")
