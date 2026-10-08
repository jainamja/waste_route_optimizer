import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_html = """                            let confHtml = isDepot ? '' : `<span style="font-size:10px; font-weight:700; padding:2px 6px; border-radius:8px; margin-left:8px; ${isConf ? 'background:#ecfdf5; color:#10b981; border:1px solid #10b981;' : (isCanc ? 'background:#fef2f2; color:#ef4444; border:1px solid #ef4444;' : 'background:#eff6ff; color:#2F5FFF; border:1px solid #2F5FFF;')}">${isConf ? 'CONFIRMED' : (isCanc ? 'CANCELLED' : 'NOT CONFIRMED')}</span>`;
                            
                            stopsListHtml += `
                                <div class="stop-item ${isDone ? 'completed' : ''}" data-id="${customer.id}" style="${isDepot ? '' : 'cursor: grab;'}">
                                    <div class="stop-status">
                                        ${isDone ? '<i class="fa-solid fa-circle-check"></i>' : '<i class="fa-regular fa-circle"></i>'}
                                    </div>
                                    <div class="stop-info" style="flex:1;">
                                        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                                            <div class="stop-name" style="display:flex; align-items:center;">${displayName}${confHtml}</div>
                                            ${!isDone && !isDepot ? `<button onclick="removeStop(${customer.id}, ${customer.truck})" style="background:none; border:none; color:#ef4444; cursor:pointer; padding:4px; margin-left:8px;" title="Remove Stop"><i class="fa-solid fa-trash"></i></button>` : ''}
                                        </div>
                                        ${customer.address ? `<div style="color:var(--text-muted); font-size:13px; margin-top:2px;"><i class="fa-solid fa-location-dot"></i> ${customer.address}</div>` : ''}
                                    </div>
                                </div>
                            `;"""

new_html = """                            let confHtml = isDepot ? '' : `<span style="font-size:10px; font-weight:700; padding:2px 6px; border-radius:8px; margin-left:8px; ${isConf ? 'background:#ecfdf5; color:#10b981; border:1px solid #10b981;' : (isCanc ? 'background:#fef2f2; color:#ef4444; border:1px solid #ef4444;' : 'background:#eff6ff; color:#2F5FFF; border:1px solid #2F5FFF;')}">${isConf ? 'CONFIRMED' : (isCanc ? 'CANCELLED' : 'NOT CONFIRMED')}</span>`;
                            
                            let isInactive = customer.customer_status === 'INACTIVE';
                            let itemStyle = isDepot ? '' : 'cursor: grab;';
                            if (isInactive) itemStyle += ' background: #fef2f2; border: 1px solid #fca5a5;';
                            let nameDec = isInactive ? 'color: #ef4444;' : '';
                            
                            let toggleHtml = isDepot ? '' : `
                            <div style="margin-top:8px;">
                                <select onchange="updateCustomerStatus(${customer.id}, this.value)" style="font-size:11px; padding:4px 8px; border-radius:12px; font-weight:700; cursor:pointer; ${isInactive ? 'background:#ef4444; color:white; border:none;' : 'background:#ecfdf5; color:#10b981; border:1px solid #10b981;'}">
                                    <option value="ACTIVE" ${!isInactive ? 'selected' : ''}>Active</option>
                                    <option value="INACTIVE" ${isInactive ? 'selected' : ''}>Inactive</option>
                                </select>
                            </div>
                            `;
                            
                            stopsListHtml += `
                                <div class="stop-item ${isDone ? 'completed' : ''}" data-id="${customer.id}" style="${itemStyle}">
                                    <div class="stop-status">
                                        ${isDone ? '<i class="fa-solid fa-circle-check"></i>' : '<i class="fa-regular fa-circle"></i>'}
                                    </div>
                                    <div class="stop-info" style="flex:1;">
                                        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                                            <div class="stop-name" style="display:flex; align-items:center; ${nameDec}">${displayName}${confHtml}</div>
                                            ${!isDone && !isDepot ? `<button onclick="removeStop(${customer.id}, ${customer.truck})" style="background:none; border:none; color:#ef4444; cursor:pointer; padding:4px; margin-left:8px;" title="Remove Stop"><i class="fa-solid fa-trash"></i></button>` : ''}
                                        </div>
                                        ${customer.address ? `<div style="color:var(--text-muted); font-size:13px; margin-top:2px;"><i class="fa-solid fa-location-dot"></i> ${customer.address}</div>` : ''}
                                        ${toggleHtml}
                                    </div>
                                </div>
                            `;"""

text = text.replace(old_html, new_html)

# Add updateCustomerStatus function
script_to_add = """
        window.updateCustomerStatus = async function(customerId, status) {
            try {
                let res = await fetch('/api/update_customer_status', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({id: customerId, customer_status: status})
                });
                let data = await res.json();
                if(data.success) {
                    refreshData();
                } else {
                    alert("Failed to update status: " + data.error);
                }
            } catch (e) {
                console.error(e);
                alert("Network error while updating status.");
            }
        };
"""

text = text.replace("window.saveTemplate = function() {", script_to_add + "\n        window.saveTemplate = function() {")

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done!")
