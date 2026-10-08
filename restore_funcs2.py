import io
import re
import subprocess

out = subprocess.check_output(["git", "show", "5dbb0b8:templates/admin_dashboard.html"]).decode('utf-8')

match = re.search(r'(        window\.deployTemplate = async function\(id\) \{[\s\S]*?        window\.deleteTemplate = async function\(id\) \{[\s\S]*?        \})', out)
if match:
    deleted_funcs = match.group(1)
    
    with io.open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
        current = f.read()
        
    new_text = current.replace("        function loadDrivers() {", deleted_funcs + "\n\n        function loadDrivers() {")
    
    with io.open('templates/admin_dashboard.html', 'w', encoding='utf-8', newline='') as f:
        f.write(new_text)
    print("Functions restored")
else:
    print("Could not find deleted functions!")
