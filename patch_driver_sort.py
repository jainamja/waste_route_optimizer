import io

with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_sort = """                stops.sort((a, b) => (a.sequence || 999) - (b.sequence || 999));"""
new_sort = """                stops.sort((a, b) => (a.sequence || 999) - (b.sequence || 999));
                
                // Assign dynamic serial number (route position)
                let dynamicSr = 1;
                stops.forEach(s => {
                    let isDepot = s.id < 0 || s.name === 'End Location / Depot';
                    if (!isDepot) {
                        s.dynamicSr = dynamicSr++;
                    }
                });"""
text = text.replace(old_sort, new_sort)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
