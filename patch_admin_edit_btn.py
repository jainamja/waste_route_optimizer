import io

with io.open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_edit = """        window.editAssignedRoute = function(id) {
            // Treat editing an assigned route identical to editing a saved template.
            // Since the assignment points to the SavedTemplate ID, editing it and saving it
            // will automatically sync to all assigned drivers.
            window.location.href = `/live?mode=edit&template_id=${id}`;
        };"""

new_edit = """        window.editAssignedRoute = function(id, truckIdStr) {
            let truckId = truckIdStr ? truckIdStr.split(',')[0] : '';
            let url = `/live?mode=edit_assigned`;
            if (truckId) url += `&truck_id=${truckId}`;
            window.location.href = url;
        };"""

text = text.replace(old_edit, new_edit)

old_btn = """<button onclick="editAssignedRoute(${r.id})" class="btn btn-outline" style="padding:8px 16px; font-size:13px; background:white;"><i class="fa-solid fa-pen"></i> Edit Route</button>"""
new_btn = """<button onclick="editAssignedRoute(${r.id}, '${r.truck_ids.join(',')}')" class="btn btn-outline" style="padding:8px 16px; font-size:13px; background:white;"><i class="fa-solid fa-pen"></i> Edit Route</button>"""

text = text.replace(old_btn, new_btn)

with io.open('templates/admin_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
