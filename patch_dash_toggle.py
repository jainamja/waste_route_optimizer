import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_fetch = """            fetch('/api/data')
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

new_fetch = """            fetch('/api/data')
                .then(res => res.json())
                .then(resData => {
                    window.currentTemplateId = resData.current_template_id;
                    window.currentTemplateName = resData.current_template_name;
                    window.isEditingTemplate = (window.currentTemplateId != null && !resData.is_from_template);

                    let nameInput = document.getElementById('template-name');
                    if (nameInput) {
                        if (window.currentTemplateName) {
                            if (!nameInput.value) nameInput.value = window.currentTemplateName;
                        } else {
                            nameInput.value = '';
                        }
                    }

                    if (resData.error || !resData.routes || resData.routes.length === 0) {"""

text = text.replace(old_fetch, new_fetch)

old_toggle = """                            let toggleHtml = isDepot ? '' : `
                            <div style="margin-top:8px;">
                                <select onchange="updateCustomerStatus(${customer.id}, this.value)" style="font-size:11px; padding:4px 8px; border-radius:12px; font-weight:700; cursor:pointer; ${isInactive ? 'background:#ef4444; color:white; border:none;' : 'background:#ecfdf5; color:#10b981; border:1px solid #10b981;'}">
                                    <option value="ACTIVE" ${!isInactive ? 'selected' : ''}>Active</option>
                                    <option value="INACTIVE" ${isInactive ? 'selected' : ''}>Inactive</option>
                                </select>
                            </div>
                            `;"""

new_toggle = """                            let toggleHtml = (isDepot || !window.isEditingTemplate) ? '' : `
                            <div style="margin-top:8px;">
                                <select onchange="updateCustomerStatus(${customer.id}, this.value)" style="font-size:11px; padding:4px 8px; border-radius:12px; font-weight:700; cursor:pointer; ${isInactive ? 'background:#ef4444; color:white; border:none;' : 'background:#ecfdf5; color:#10b981; border:1px solid #10b981;'}">
                                    <option value="ACTIVE" ${!isInactive ? 'selected' : ''}>Active</option>
                                    <option value="INACTIVE" ${isInactive ? 'selected' : ''}>Inactive</option>
                                </select>
                            </div>
                            `;"""

text = text.replace(old_toggle, new_toggle)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
