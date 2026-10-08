import io

with io.open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_html = """        <!-- Driver Management -->
        <div>
            <div class="section-header">
                <h2>Driver Management</h2>"""

new_html = """        <!-- Assigned Routes -->
        <div>
            <div class="section-header">
                <h2>Assigned Routes</h2>
            </div>
            <div class="driver-list" id="assigned-routes-list">
                <div style="padding: 24px; text-align: center; color: var(--text-muted);">Loading assignments...</div>
            </div>
        </div>

        <!-- Driver Management -->
        <div>
            <div class="section-header">
                <h2>Driver Management</h2>"""

text = text.replace(old_html, new_html)

old_modal = """    <!-- Modal -->
    <div id="add-driver-modal">"""

new_modal = """    <!-- Assign Route Modal -->
    <div id="assign-route-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:9999; align-items:center; justify-content:center;">
        <div class="modal-content" style="background:white; padding:24px; border-radius:16px; max-width:400px; width:90%; box-shadow:0 10px 25px rgba(0,0,0,0.2);">
            <h3 style="margin-top:0; font-family:'Manrope', sans-serif;">Assign Route</h3>
            <p style="color:var(--text-muted); font-size:14px; margin-bottom:24px;">Select a saved route for this driver.</p>
            <input type="hidden" id="assign-driver-id">
            <select id="assign-template-select" style="width:100%; padding:12px; border:1px solid var(--border); border-radius:8px; margin-bottom:24px; font-family:'Inter', sans-serif;">
                <option value="">No Route Assigned</option>
            </select>
            <div style="display:flex; gap:12px;">
                <button class="btn btn-primary" onclick="saveAssignment()" style="flex:1; justify-content:center;">Save</button>
                <button class="btn btn-outline" onclick="document.getElementById('assign-route-modal').style.display='none'" style="flex:1; justify-content:center;">Cancel</button>
            </div>
        </div>
    </div>

    <!-- Modal -->
    <div id="add-driver-modal">"""

text = text.replace(old_modal, new_modal)

with io.open('templates/admin_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
