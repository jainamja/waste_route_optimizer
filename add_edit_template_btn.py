import os

filepath = 'templates/admin_dashboard.html'
content = open(filepath, 'r', encoding='utf-8').read()

old_button = """                                        <button onclick="deployTemplate(${t.id})" class="btn btn-primary" style="padding:8px 16px; font-size:14px;"><i class="fa-solid fa-paper-plane"></i> Deploy</button>
                                        <button onclick="deleteTemplate(${t.id})" style="background:none; border:none; color:var(--red, #ef4444); cursor:pointer; font-size:16px; padding:4px;" title="Delete Template"><i class="fa-solid fa-trash-can"></i></button>"""

new_button = """                                        <button onclick="deployTemplate(${t.id})" class="btn btn-primary" style="padding:8px 16px; font-size:14px;"><i class="fa-solid fa-paper-plane"></i> Deploy</button>
                                        <button onclick="editTemplate(${t.id})" class="btn btn-outline" style="padding:8px 16px; font-size:14px; background:white;"><i class="fa-solid fa-pen"></i> Edit</button>
                                        <button onclick="deleteTemplate(${t.id})" style="background:none; border:none; color:var(--red, #ef4444); cursor:pointer; font-size:16px; padding:4px;" title="Delete Template"><i class="fa-solid fa-trash-can"></i></button>"""

content = content.replace(old_button, new_button)

old_js = """        window.deployTemplate = async function(id) {
            if(!confirm("Are you sure you want to deploy this template? This will OVERWRITE your currently active routes!")) return;
            
            try {
                let res = await fetch('/api/deploy_template/' + id, { method: 'POST' });"""

new_js = """        window.deployTemplate = async function(id) {
            if(!confirm("Are you sure you want to deploy this template? This will OVERWRITE your currently active routes!")) return;
            
            try {
                let res = await fetch('/api/deploy_template/' + id + '?mode=deploy', { method: 'POST' });"""

content = content.replace(old_js, new_js)

old_js2 = """            } catch(e) {
                alert("An error occurred");
            }
        };

        window.deleteTemplate = async function(id) {"""

new_js2 = """            } catch(e) {
                alert("An error occurred");
            }
        };

        window.editTemplate = async function(id) {
            if(!confirm("Are you sure you want to edit this template? This will OVERWRITE your currently active routes and take you to the Route Dashboard to make changes.")) return;
            
            try {
                let res = await fetch('/api/deploy_template/' + id + '?mode=edit', { method: 'POST' });
                let data = await res.json();
                if(data.success) {
                    window.location.href = '/routes';
                } else {
                    alert("Error: " + data.error);
                }
            } catch(e) {
                alert("An error occurred");
            }
        };

        window.deleteTemplate = async function(id) {"""
content = content.replace(old_js2, new_js2)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS")
