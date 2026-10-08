import io
import re

with io.open('admin_dashboard_old.html', 'r', encoding='utf-8') as f:
    old_text = f.read()

match = re.search(r'(        window\.deployTemplate = async function\(id\) \{[\s\S]*?        window\.deleteTemplate = async function\(id\) \{[\s\S]*?        \})', old_text)
if match:
    deleted_funcs = match.group(1)
    
    with io.open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
        current = f.read()
        
    # Insert right before function loadDrivers
    new_text = current.replace("        function loadDrivers() {", deleted_funcs + "\n\n        function loadDrivers() {")
    
    with io.open('templates/admin_dashboard.html', 'w', encoding='utf-8', newline='') as f:
        f.write(new_text)
    print("Functions restored")
else:
    print("Could not find deleted functions!")
