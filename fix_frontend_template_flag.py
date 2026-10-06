import os

filepath = 'templates/live_dashboard.html'
content = open(filepath, 'r', encoding='utf-8').read()

old_logic = """                    setDisplay('export-btn', 'inline-flex');
                    setDisplay('add-stop-btn', 'inline-flex');
                    setDisplay('save-template-btn', 'inline-flex');"""

new_logic = """                    setDisplay('export-btn', 'inline-flex');
                    setDisplay('add-stop-btn', 'inline-flex');
                    setDisplay('save-template-btn', resData.is_from_template ? 'none' : 'inline-flex');"""

content = content.replace(old_logic, new_logic)
open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS")
