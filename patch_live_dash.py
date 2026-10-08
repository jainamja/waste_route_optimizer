import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_isEditing = "window.isEditingTemplate = (window.currentTemplateId != null && !resData.is_from_template);"
new_isEditing = """let urlParams = new URLSearchParams(window.location.search);
                    let isEditAssigned = urlParams.get('mode') === 'edit_assigned';
                    window.isEditingTemplate = (window.currentTemplateId != null && (!resData.is_from_template || isEditAssigned));"""

text = text.replace(old_isEditing, new_isEditing)

# Also rename "Save as Template" button to "Save Assigned Route" dynamically
old_save_btn = """let toggleHtml = (isDepot || !window.isEditingTemplate) ? '' : `"""
new_save_btn = """if (isEditAssigned) {
                        let btn = document.querySelector('button[onclick="document.getElementById(\\'save-template-modal\\').style.display=\\'flex\\'"]');
                        if (btn) btn.innerHTML = '<i class="fa-solid fa-save"></i> Save Assigned Route';
                    }
                    let toggleHtml = (isDepot || !window.isEditingTemplate) ? '' : `"""

text = text.replace(old_save_btn, new_save_btn)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
