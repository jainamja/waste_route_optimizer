import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_save = """        window.saveTemplate = function() {
            let name = document.getElementById('template-name').value;
            if(!name) { alert("Enter a name"); return; }
            
            let btn = document.getElementById('btn-save-template');
            btn.disabled = true;
            btn.innerText = "Saving...";
            
            fetch('/api/save_template', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: name})
            }).then(r => r.json()).then(res => {
                if(res.success) {
                    alert("Template saved! You can load it anytime from the Control Panel.");
                    document.getElementById('save-template-modal').style.display = 'none';
                    document.getElementById('template-name').value = '';
                } else {
                    alert("Error: " + res.error);
                }
            }).catch(e => alert("Network Error")).finally(() => {
                btn.disabled = false;
                btn.innerText = "Save";
            });
        };"""

new_save = """        window.saveTemplate = function() {
            let name = document.getElementById('template-name').value;
            if(!name) { alert("Enter a name"); return; }
            
            let btn = document.getElementById('btn-save-template');
            btn.disabled = true;
            btn.innerText = "Saving...";
            
            let payload = {name: name};
            if (window.currentTemplateId) {
                payload.id = window.currentTemplateId;
            }
            
            fetch('/api/save_template', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            }).then(r => r.json()).then(res => {
                if(res.success) {
                    alert("Template saved! You can load it anytime from the Control Panel.");
                    document.getElementById('save-template-modal').style.display = 'none';
                    document.getElementById('template-name').value = '';
                } else {
                    alert("Error: " + res.error);
                }
            }).catch(e => alert("Network Error")).finally(() => {
                btn.disabled = false;
                btn.innerText = "Save";
            });
        };"""

text = text.replace(old_save, new_save)

old_fetch = """            fetch('/api/data')
                .then(res => res.json())
                .then(resData => {
                    if (resData.error || !resData.routes || resData.routes.length === 0) {"""

new_fetch = """            fetch('/api/data')
                .then(res => res.json())
                .then(resData => {
                    if (resData.is_from_template) {
                        window.currentTemplateId = resData.current_template_id;
                        window.currentTemplateName = resData.current_template_name;
                        if (window.currentTemplateName) {
                            let nameInput = document.getElementById('template-name');
                            if (nameInput && !nameInput.value) nameInput.value = window.currentTemplateName;
                        }
                    } else {
                        window.currentTemplateId = null;
                        window.currentTemplateName = null;
                        let nameInput = document.getElementById('template-name');
                        if (nameInput) nameInput.value = '';
                    }

                    if (resData.error || !resData.routes || resData.routes.length === 0) {"""

text = text.replace(old_fetch, new_fetch)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
