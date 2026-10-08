import io

with io.open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_script = """        function loadDrivers() {
            fetch('/api/drivers')
                .then(res => res.json())
                .then(data => {
                    let html = '';
                    if (data.drivers.length === 0) {
                        html = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">No drivers created yet.</div>';
                    } else {
                        data.drivers.forEach(d => {
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

new_script = """        let currentTemplates = [];
        let currentDrivers = [];
        
        function loadTemplates() {
            fetch('/api/templates')
                .then(res => res.json())
                .then(data => {
                    currentTemplates = data.templates || [];
                    let html = '';
                    if (!data.templates || data.templates.length === 0) {
                        html = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">No saved templates yet. Go to Route Dashboard to save one.</div>';
                    } else {
                        data.templates.forEach(t => {
                            html += `
                                <div class="driver-item">
                                    <div class="driver-info">
                                        <div class="driver-avatar" style="background:#f1f5f9; color:var(--primary);"><i class="fa-solid fa-route"></i></div>
                                        <div class="driver-details">
                                            <h4>${t.name}</h4>
                                            <p>Saved on ${t.created_at}</p>
                                        </div>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:12px;">
                                        <button onclick="deployTemplate(${t.id})" class="btn btn-primary" style="padding:8px 16px; font-size:14px;"><i class="fa-solid fa-paper-plane"></i> Deploy</button>
                                        <button onclick="editTemplate(${t.id})" class="btn btn-outline" style="padding:8px 16px; font-size:14px; background:white;"><i class="fa-solid fa-pen"></i> Edit</button>
                                        <button onclick="deleteTemplate(${t.id})" style="background:none; border:none; color:var(--red, #ef4444); cursor:pointer; font-size:16px; padding:4px;" title="Delete Template"><i class="fa-solid fa-trash-can"></i></button>
                                    </div>
                                </div>
                            `;
                        });
                    }
                    document.getElementById('template-list').innerHTML = html;
                    updateAssignModalOptions();
                });
        }

        function loadDrivers() {
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
        }
        
        function updateAssignModalOptions() {
            let select = document.getElementById('assign-template-select');
            if (!select) return;
            let html = '<option value="">No Route Assigned</option>';
            currentTemplates.forEach(t => {
                html += `<option value="${t.id}">${t.name}</option>`;
            });
            select.innerHTML = html;
        }
        
        window.openAssignModal = function(driverId, currentTemplateId) {
            document.getElementById('assign-driver-id').value = driverId;
            let select = document.getElementById('assign-template-select');
            select.value = currentTemplateId || "";
            document.getElementById('assign-route-modal').style.display = 'flex';
        };
        
        window.saveAssignment = function() {
            let driverId = document.getElementById('assign-driver-id').value;
            let templateId = document.getElementById('assign-template-select').value;
            
            fetch('/api/assign_route', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    driver_id: driverId,
                    template_id: templateId || null
                })
            }).then(r => r.json()).then(res => {
                if(res.success) {
                    document.getElementById('assign-route-modal').style.display = 'none';
                    loadDrivers();
                } else {
                    alert("Error: " + res.error);
                }
            }).catch(e => alert("Network Error"));
        };"""

# Replace the whole loadTemplates and loadDrivers block
import re
text = re.sub(r'        function loadTemplates\(\) \{[\s\S]*?document\.getElementById\(\'driver-list\'\)\.innerHTML = html;\s*\}\);\s*\}', new_script, text)

with io.open('templates/admin_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
