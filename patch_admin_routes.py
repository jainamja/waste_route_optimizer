import io
import re

with io.open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_script = """        function loadDrivers() {
            fetch('/api/drivers')
                .then(res => res.json())
                .then(data => {
                    currentDrivers = data.drivers || [];
                    let html = '';
                    let assignHtml = '';
                    
                    if (currentDrivers.length === 0) {
                        html = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">No drivers created yet.</div>';
                        assignHtml = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">No drivers available to assign.</div>';
                    } else {
                        currentDrivers.forEach(d => {
                            html += `
                                <div class="driver-item">
                                    <div class="driver-info">
                                        <div class="driver-avatar"><i class="fa-solid fa-user"></i></div>
                                        <div class="driver-details">
                                            <h4>${d.name || 'Unknown Driver'} <span style="font-size:13px; font-weight:normal; color:var(--text-muted); padding-left:4px;">(${d.username})</span></h4>
                                            <p>Password: ${d.password_hash === 'redacted' ? '********' : 'Stored securely'}</p>
                                        </div>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:12px;">
                                        <div class="driver-badge">Truck ID: ${d.truck_id}</div>
                                        <button onclick="deleteDriver(${d.id})" style="background:none; border:none; color:var(--red, #ef4444); cursor:pointer; font-size:16px; padding:4px;" title="Delete Driver"><i class="fa-solid fa-trash-can"></i></button>
                                    </div>
                                </div>
                            `;
                            
                            let isUnassigned = !d.assigned_template_id;
                            assignHtml += `
                                <div class="driver-item" style="border-left: 4px solid ${isUnassigned ? 'var(--amber, #FFA93E)' : 'var(--primary, #2F5FFF)'}">
                                    <div class="driver-info">
                                        <div class="driver-details">
                                            <h4>${d.name || 'Unknown Driver'} <span style="font-size:13px; font-weight:normal; color:var(--text-muted); padding-left:4px;">(Truck ${d.truck_id})</span></h4>
                                            <p style="margin-top:4px; font-weight:600; color:${isUnassigned ? 'var(--amber, #FFA93E)' : 'var(--text-main)'}">Assigned Route: ${d.assigned_template_name}</p>
                                        </div>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:12px;">
                                        <button onclick="openAssignModal(${d.id}, ${d.assigned_template_id || 'null'})" class="btn btn-outline" style="padding:8px 16px; font-size:13px; background:white;"><i class="fa-solid fa-pen"></i> ${isUnassigned ? 'Assign Route' : 'Change Route'}</button>
                                    </div>
                                </div>
                            `;
                        });
                    }
                    document.getElementById('driver-list').innerHTML = html;
                    document.getElementById('assigned-routes-list').innerHTML = assignHtml;
                });
        }"""

new_script = """        function loadAssignedRoutes() {
            fetch('/api/assigned_routes')
                .then(res => res.json())
                .then(data => {
                    let html = '';
                    if (!data.assigned_routes || data.assigned_routes.length === 0) {
                        html = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">No routes are currently assigned.</div>';
                    } else {
                        data.assigned_routes.forEach(r => {
                            html += `
                                <div class="driver-item" style="border-left: 4px solid var(--primary);">
                                    <div class="driver-info">
                                        <div class="driver-details">
                                            <h4>${r.name}</h4>
                                            <p style="margin-top:4px; color:var(--text-muted);">${r.stops_count} Stops</p>
                                        </div>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:12px;">
                                        <button onclick="editAssignedRoute(${r.id})" class="btn btn-outline" style="padding:8px 16px; font-size:13px; background:white;"><i class="fa-solid fa-pen"></i> Edit Route</button>
                                    </div>
                                </div>
                            `;
                        });
                    }
                    document.getElementById('assigned-routes-list').innerHTML = html;
                });
        }

        window.editAssignedRoute = function(id) {
            // Treat editing an assigned route identical to editing a saved template.
            // Since the assignment points to the SavedTemplate ID, editing it and saving it
            // will automatically sync to all assigned drivers.
            window.location.href = `/live?mode=edit&template_id=${id}`;
        };

        function loadDrivers() {
            fetch('/api/drivers')
                .then(res => res.json())
                .then(data => {
                    currentDrivers = data.drivers || [];
                    let html = '';
                    
                    if (currentDrivers.length === 0) {
                        html = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">No drivers created yet.</div>';
                    } else {
                        currentDrivers.forEach(d => {
                            html += `
                                <div class="driver-item">
                                    <div class="driver-info">
                                        <div class="driver-avatar"><i class="fa-solid fa-user"></i></div>
                                        <div class="driver-details">
                                            <h4>${d.name || 'Unknown Driver'} <span style="font-size:13px; font-weight:normal; color:var(--text-muted); padding-left:4px;">(${d.username})</span></h4>
                                            <p>Password: ${d.password_hash === 'redacted' ? '********' : 'Stored securely'}</p>
                                        </div>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:12px;">
                                        <div class="driver-badge">Truck ID: ${d.truck_id}</div>
                                        <button onclick="deleteDriver(${d.id})" style="background:none; border:none; color:var(--red, #ef4444); cursor:pointer; font-size:16px; padding:4px;" title="Delete Driver"><i class="fa-solid fa-trash-can"></i></button>
                                    </div>
                                </div>
                            `;
                        });
                    }
                    document.getElementById('driver-list').innerHTML = html;
                });
        }"""

text = text.replace(old_script, new_script)

with io.open('templates/admin_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
