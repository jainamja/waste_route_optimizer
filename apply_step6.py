import os
import re

filepath = 'templates/live_dashboard.html'
content = open(filepath, 'r', encoding='utf-8').read()

# 1. Update trucksInfo initialization and counting
old_loop = """            data.customers.forEach(c => {
                let t = c.truck;
                if (!trucksInfo[t]) trucksInfo[t] = { total: 0, completed: 0 };
                trucksInfo[t].total++;
                if (c.status === 'COMPLETED') trucksInfo[t].completed++;
            });"""
new_loop = """            data.customers.forEach(c => {
                let t = c.truck;
                if (!trucksInfo[t]) trucksInfo[t] = { total: 0, completed: 0, confirmed: 0, realCount: 0 };
                trucksInfo[t].total++;
                if (c.status === 'COMPLETED') trucksInfo[t].completed++;
                if (c.id > -1000 && c.name !== 'End Location / Depot') {
                    trucksInfo[t].realCount++;
                    if (c.confirmation === 'CONFIRMED') trucksInfo[t].confirmed++;
                }
            });"""
content = content.replace(old_loop, new_loop)

# 2. Update the stopsListHtml inside the renderSidebar loop
old_stop_item = """                            stopsListHtml += `
                                <div class="stop-item ${isDone ? 'completed' : ''}" data-id="${customer.id}" style="${isDepot ? '' : 'cursor: grab;'}">
                                    <div class="stop-status">
                                        ${isDone ? '<i class="fa-solid fa-circle-check"></i>' : '<i class="fa-regular fa-circle"></i>'}
                                    </div>
                                    <div class="stop-info" style="flex:1;">
                                        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                                            <div class="stop-name">${displayName}</div>
                                            ${!isDone && !isDepot ? `<button onclick="removeStop(${customer.id}, ${customer.truck})" style="background:none; border:none; color:#ef4444; cursor:pointer; padding:4px; margin-left:8px;" title="Remove Stop"><i class="fa-solid fa-trash"></i></button>` : ''}
                                        </div>
                                        ${customer.address ? `<div style="color:var(--text-muted); font-size:13px; margin-top:2px;"><i class="fa-solid fa-location-dot"></i> ${customer.address}</div>` : ''}
                                    </div>
                                </div>
                            `;"""
new_stop_item = """                            let isConf = customer.confirmation === 'CONFIRMED';
                            let confHtml = isDepot ? '' : `<span style="font-size:10px; font-weight:700; padding:2px 6px; border-radius:8px; margin-left:8px; ${isConf ? 'background:#ecfdf5; color:#10b981; border:1px solid #10b981;' : 'background:#eff6ff; color:#2F5FFF; border:1px solid #2F5FFF;'}">${isConf ? 'CONFIRMED' : 'NOT CONFIRMED'}</span>`;
                            
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
content = content.replace(old_stop_item, new_stop_item)

# 3. Update the truck header and buttons
old_truck_meta = """                        <div class="truck-meta">
                            ${distStr}
                        </div>"""
new_truck_meta = """                        <div class="truck-meta">
                            ${distStr}
                            <span style="font-size:12px; font-weight:600; padding:2px 8px; border-radius:12px; background:#f1f5f9; color:var(--text-main);">${info.confirmed} confirmed &middot; ${info.realCount - info.confirmed} not</span>
                        </div>"""
content = content.replace(old_truck_meta, new_truck_meta)

old_buttons = """                        <div style="display:flex;gap:10px;margin-top:16px;">
                            <a href="${dirUrl}" target="_blank" style="flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:10px 0;border:1px solid var(--border);border-radius:10px;text-decoration:none;color:var(--text-main);font-size:13px;font-weight:600;background:white;">
                                <i class="fa-solid fa-map-location-dot" style="color:var(--primary);"></i> Overview
                            </a>
                            <button onclick="openAssignModal('${t}')" style="flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:10px 0;border:none;border-radius:10px;background:var(--primary);color:white;font-size:13px;font-weight:600;cursor:pointer;font-family:Inter,sans-serif;">
                                <i class="fa-solid fa-user-check"></i> Assign Driver
                            </button>
                        </div>"""
new_buttons = """                        <div style="display:flex;gap:10px;margin-top:16px;">
                            <button onclick="openAssignModal('${t}')" style="flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:10px 0;border:none;border-radius:10px;background:var(--primary);color:white;font-size:13px;font-weight:600;cursor:pointer;font-family:Inter,sans-serif;">
                                <i class="fa-solid fa-user-check"></i> Assign Driver
                            </button>
                        </div>
                        <div style="display:flex;gap:10px;margin-top:10px;">
                            <button onclick="openConfirmationsModal('${t}')" style="flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:10px 0;border:1px solid var(--border);border-radius:10px;text-decoration:none;color:var(--text-main);font-size:13px;font-weight:600;background:white;cursor:pointer;">
                                <i class="fa-solid fa-list-check"></i> Edit confirmations
                            </button>
                            <a href="${dirUrl}" target="_blank" style="flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:10px 0;border:1px solid var(--border);border-radius:10px;text-decoration:none;color:var(--text-main);font-size:13px;font-weight:600;background:white;">
                                <i class="fa-solid fa-map-location-dot" style="color:var(--primary);"></i> Map
                            </a>
                        </div>"""
content = content.replace(old_buttons, new_buttons)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS Step 6")
