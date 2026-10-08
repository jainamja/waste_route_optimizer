import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Remove Stop number from marker
old_marker = """<h4>${c.name} <span style="color:var(--text-muted); font-size:12px; font-weight:500;">(Stop ${c.stop_number})</span></h4>"""
new_marker = """<h4>${c.name}</h4>"""
text = text.replace(old_marker, new_marker)

# Fix manual target dropdown
old_dropdown = """                        let sorted = trucks[truckId].sort((a,b) => a.stop_number - b.stop_number);
                        sorted.forEach(s => {
                            if(s.status === 'PENDING') {
                                let opt = document.createElement('option');
                                opt.value = truckId + "|" + s.stop_number;
                                opt.text = "After Stop " + s.stop_number + ": " + s.name;
                                optgroup.appendChild(opt);
                            }
                        });"""

new_dropdown = """                        let sorted = trucks[truckId].sort((a,b) => a.stop_number - b.stop_number);
                        let dynIdx = 1;
                        sorted.forEach(s => {
                            let currentIdx = dynIdx++;
                            if(s.status === 'PENDING') {
                                let opt = document.createElement('option');
                                opt.value = truckId + "|" + s.stop_number;
                                opt.text = "After Stop " + currentIdx + ": " + s.name;
                                optgroup.appendChild(opt);
                            }
                        });"""

text = text.replace(old_dropdown, new_dropdown)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
