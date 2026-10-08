import io

with io.open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("loadDrivers();\n            loadTemplates();", "loadDrivers();\n            loadTemplates();\n            loadAssignedRoutes();")

with io.open('templates/admin_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
