import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_loop = """            let html = '';
            arr.forEach(c => {"""

new_loop = """            let html = '';
            arr.forEach((c, idx) => {
                let currentSr = idx + 1;"""

text = text.replace(old_loop, new_loop)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
