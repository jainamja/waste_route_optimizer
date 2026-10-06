import os

filepath = 'templates/admin_dashboard.html'
content = open(filepath, 'r', encoding='utf-8').read()

# 1. Add the Saved Templates Section
old_driver_management = """        <!-- Driver Management -->
        <div>
            <div class="section-header">
                <h2>Driver Management</h2>"""

new_templates_section = """        <!-- Saved Templates -->
        <div>
            <div class="section-header">
                <h2>Saved Templates Library</h2>
            </div>
            <div class="driver-list" id="template-list">
                <div style="padding: 24px; text-align: center; color: var(--text-muted);">Loading templates...</div>
            </div>
        </div>

        <!-- Driver Management -->
        <div>
            <div class="section-header">
                <h2>Driver Management</h2>"""
                
content = content.replace(old_driver_management, new_templates_section)

# 2. Add the JS functions
old_script_start = """    <script>
        function loadDrivers() {"""
        
new_script_start = """    <script>
        function loadTemplates() {
            fetch('/api/templates')
                .then(res => res.json())
                .then(data => {
                    let html = '';
                    if (!data.templates || data.templates.length === 0) {
                        html = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">No saved templates yet. Go to Route Dashboard to save one.</div>';
                    } else {
                        data.templates.forEach(t => {
                            html += `
                                <div class="driver-item">
                                    <div class="driver-info">
                                        <div class="driver-avatar" style="background:#eef2ff; color:#4f46e5;"><i class="fa-solid fa-bookmark"></i></div>
                                        <div class="driver-details">
                                            <h4>${t.name}</h4>
                                            <p>Saved on: ${t.created_at}</p>
                                        </div>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:12px;">
                                        <button onclick="deployTemplate(${t.id})" class="btn btn-primary" style="padding:8px 16px; font-size:14px;"><i class="fa-solid fa-paper-plane"></i> Deploy</button>
                                        <button onclick="deleteTemplate(${t.id})" style="background:none; border:none; color:var(--red, #ef4444); cursor:pointer; font-size:16px; padding:4px;" title="Delete Template"><i class="fa-solid fa-trash-can"></i></button>
                                    </div>
                                </div>
                            `;
                        });
                    }
                    document.getElementById('template-list').innerHTML = html;
                });
        }

        window.deployTemplate = async function(id) {
            if(!confirm("Are you sure you want to deploy this template? This will OVERWRITE your currently active routes!")) return;
            
            try {
                let res = await fetch('/api/deploy_template/' + id, { method: 'POST' });
                let data = await res.json();
                if(data.success) {
                    alert("Template deployed successfully! Drivers can now see it in their app.");
                    window.location.href = '/routes';
                } else {
                    alert("Error: " + data.error);
                }
            } catch(e) {
                alert("An error occurred");
            }
        };

        window.deleteTemplate = async function(id) {
            if(!confirm("Are you sure you want to permanently delete this template?")) return;
            
            try {
                let res = await fetch('/api/delete_template/' + id, { method: 'DELETE' });
                let data = await res.json();
                if(data.success) {
                    loadTemplates();
                } else {
                    alert("Error: " + data.error);
                }
            } catch(e) {
                alert("An error occurred");
            }
        };

        function loadDrivers() {"""
        
content = content.replace(old_script_start, new_script_start)

# 3. Add to window.onload
old_onload = """        window.onload = loadDrivers;"""
new_onload = """        window.onload = function() {
            loadDrivers();
            loadTemplates();
        };"""
        
content = content.replace(old_onload, new_onload)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS")
