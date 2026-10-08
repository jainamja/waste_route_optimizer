import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(1250, 1280):
    print(lines[i].strip())
