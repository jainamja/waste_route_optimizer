import io
import re
import subprocess

out = subprocess.check_output(["git", "show", "5dbb0b8:templates/admin_dashboard.html"]).decode('utf-8')

match = re.search(r'(        window\.deployTemplate = async function\(id\) \{[\s\S]*?        window\.deleteTemplate = async function\(id\) \{[\s\S]*?        \};)', out)
if match:
    deleted_funcs = match.group(1)
    
    with io.open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
        current = f.read()
        
    # Replace the mangled part
    current = re.sub(r'        window\.deployTemplate = async function\(id\) \{[\s\S]*?        function loadDrivers\(\) \{', deleted_funcs + "\n\n        function loadDrivers() {", current)
    
    with io.open('templates/admin_dashboard.html', 'w', encoding='utf-8', newline='') as f:
        f.write(current)
    print("Fixed syntax")
else:
    print("Match failed")
