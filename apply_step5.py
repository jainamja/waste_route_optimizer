import os
import re

filepath = 'templates/live_dashboard.html'
content = open(filepath, 'r', encoding='utf-8').read()

# 1. Update the Assign Modal
old_assign_modal = """            <div style="display:flex; gap:12px;">
                <button id="btn-assign-confirm" onclick="assignDriver()" style="flex:1; background:var(--primary); color:white; border:none; padding:12px; border-radius:10px; font-weight:700; font-size:15px; cursor:pointer; font-family:'Inter',sans-serif;">Assign</button>
                <button onclick="document.getElementById('assign-driver-modal').style.display='none'" style="flex:1; background:#f1f5f9; color:var(--text-main); border:none; padding:12px; border-radius:10px; font-weight:600; font-size:15px; cursor:pointer; font-family:'Inter',sans-serif;">Cancel</button>
            </div>"""
new_assign_modal = """            <div style="display:flex; gap:12px;">
                <button id="btn-assign-next" onclick="openConfirmationsModal()" style="flex:1; background:var(--primary); color:white; border:none; padding:12px; border-radius:10px; font-weight:700; font-size:15px; cursor:pointer; font-family:'Inter',sans-serif;">Next <i class="fa-solid fa-arrow-right"></i></button>
                <button onclick="document.getElementById('assign-driver-modal').style.display='none'" style="flex:1; background:#f1f5f9; color:var(--text-main); border:none; padding:12px; border-radius:10px; font-weight:600; font-size:15px; cursor:pointer; font-family:'Inter',sans-serif;">Cancel</button>
            </div>"""
content = content.replace(old_assign_modal, new_assign_modal)

# 2. Add the Confirmations Modal HTML below the Assign Modal
new_confirmations_modal = """
    <!-- Confirmations Modal -->
    <div id="confirmations-modal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.5); z-index:9999; align-items:center; justify-content:center;">
        <div style="background:white; padding:24px; border-radius:20px; max-width:500px; width:95%; max-height:90vh; display:flex; flex-direction:column;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <h3 style="margin:0; font-family:'Manrope',sans-serif;" id="conf-modal-title">Confirm customers</h3>
                <span id="conf-counts" style="font-size:13px; font-weight:600; padding:6px 12px; border-radius:20px; background:#f1f5f9; color:var(--text-main);">0 confirmed &middot; 0 not</span>
            </div>
            
            <div style="display:flex; gap:8px; margin-bottom:16px;">
                <input type="text" id="conf-search" placeholder="Search..." onkeyup="renderConfList()" style="flex:1; padding:10px 12px; border:1px solid var(--border); border-radius:8px; font-family:'Inter',sans-serif; font-size:14px;">
                <select id="conf-filter" onchange="renderConfList()" style="padding:10px; border:1px solid var(--border); border-radius:8px; font-family:'Inter',sans-serif; font-size:14px; background:white;">
                    <option value="all">All</option>
                    <option value="confirmed">Confirmed</option>
                    <option value="not">Not confirmed</option>
                </select>
                <button onclick="markAllConf()" class="btn btn-outline" style="padding:10px;"><i class="fa-solid fa-check-double"></i></button>
            </div>
            
            <div id="conf-list" style="flex:1; overflow-y:auto; border:1px solid var(--border); border-radius:12px; background:#f8fafc; padding:8px; display:flex; flex-direction:column; gap:8px;">
                <!-- rows injected via js -->
            </div>
            
            <div style="display:flex; gap:12px; margin-top:20px;">
                <button id="btn-conf-back" onclick="goBackToAssign()" style="flex:1; background:#f1f5f9; color:var(--text-main); border:none; padding:12px; border-radius:10px; font-weight:600; font-size:15px; cursor:pointer; font-family:'Inter',sans-serif;">Back</button>
                <button onclick="closeConfModal()" style="flex:1; background:#f1f5f9; color:var(--text-main); border:none; padding:12px; border-radius:10px; font-weight:600; font-size:15px; cursor:pointer; font-family:'Inter',sans-serif;">Cancel</button>
                <button id="btn-conf-save" onclick="saveConfirmationsAndAssign()" style="flex:1.5; background:var(--primary); color:white; border:none; padding:12px; border-radius:10px; font-weight:700; font-size:15px; cursor:pointer; font-family:'Inter',sans-serif;">Assign & Save</button>
            </div>
        </div>
    </div>
"""
content = content.replace('<!-- Modal for Driver Link -->', new_confirmations_modal + '\n    <!-- Modal for Driver Link -->')

# 3. Add JS logic for the new modal
old_assign_js = """        window.assignDriver = async function() {
            let modal = document.getElementById('assign-driver-modal');
            let driverId = document.getElementById('assign-driver-select').value;
            let truckId = modal.dataset.truckId;
            let btn = document.getElementById('btn-assign-confirm');
            if (!driverId) { alert('Please select a driver'); return; }
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
            try {
                let res = await fetch('/api/assign_driver', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({driver_id: driverId, truck_id: truckId})
                });
                let result = await res.json();
                if(result.success) {
                    modal.style.display = 'none';
                    loadData();
                } else {
                    alert("Error: " + result.error);
                }
            } catch(e) {
                alert("An error occurred");
            }
            btn.disabled = false;
            btn.innerText = 'Assign';
        };"""
        
new_assign_js = """
        let currentConfData = {};
        let currentConfTruck = null;
        let currentConfDriver = null;
        let currentConfIsEditOnly = false;
        
        window.openConfirmationsModal = function(editOnlyTruckId = null) {
            let truckId = editOnlyTruckId;
            let driverId = null;
            
            if (!editOnlyTruckId) {
                // Coming from assign driver Step 1
                let modal = document.getElementById('assign-driver-modal');
                driverId = document.getElementById('assign-driver-select').value;
                truckId = modal.dataset.truckId;
                if (!driverId) { alert('Please select a driver'); return; }
                modal.style.display = 'none';
            }
            
            currentConfTruck = truckId;
            currentConfDriver = driverId;
            currentConfIsEditOnly = !!editOnlyTruckId;
            
            document.getElementById('conf-modal-title').innerText = "Confirm customers for Truck " + truckId;
            
            let saveBtn = document.getElementById('btn-conf-save');
            let backBtn = document.getElementById('btn-conf-back');
            if (currentConfIsEditOnly) {
                saveBtn.innerText = "Save Confirmations";
                backBtn.style.display = 'none';
            } else {
                saveBtn.innerText = "Assign & Save";
                backBtn.style.display = 'block';
            }
            
            // Build customers array
            currentConfData = {};
            data.customers.forEach(c => {
                if (String(c.truck) === String(truckId) && c.id > -1000 && c.name !== 'End Location / Depot') {
                    currentConfData[c.id] = {
                        id: c.id,
                        name: c.name,
                        address: c.address,
                        phone: c.phone,
                        stop_number: c.stop_number,
                        confirmation: c.confirmation || 'NOT_CONFIRMED'
                    };
                }
            });
            
            document.getElementById('conf-search').value = '';
            document.getElementById('conf-filter').value = 'all';
            
            document.getElementById('confirmations-modal').style.display = 'flex';
            renderConfList();
        };
        
        window.goBackToAssign = function() {
            document.getElementById('confirmations-modal').style.display = 'none';
            document.getElementById('assign-driver-modal').style.display = 'flex';
        };
        
        window.closeConfModal = function() {
            document.getElementById('confirmations-modal').style.display = 'none';
        };
        
        window.toggleConf = function(id) {
            let c = currentConfData[id];
            c.confirmation = (c.confirmation === 'CONFIRMED') ? 'NOT_CONFIRMED' : 'CONFIRMED';
            renderConfList();
        };
        
        window.markAllConf = function() {
            Object.values(currentConfData).forEach(c => c.confirmation = 'CONFIRMED');
            renderConfList();
        };
        
        window.renderConfList = function() {
            let search = document.getElementById('conf-search').value.toLowerCase();
            let filter = document.getElementById('conf-filter').value;
            
            let arr = Object.values(currentConfData).sort((a,b) => (a.stop_number||999) - (b.stop_number||999));
            
            let confirmedCount = arr.filter(c => c.confirmation === 'CONFIRMED').length;
            let notCount = arr.length - confirmedCount;
            document.getElementById('conf-counts').innerText = `${confirmedCount} confirmed · ${notCount} not`;
            
            let html = '';
            arr.forEach(c => {
                let match = c.name.toLowerCase().includes(search) || (c.address||'').toLowerCase().includes(search) || (c.phone||'').toLowerCase().includes(search);
                if (!match) return;
                if (filter === 'confirmed' && c.confirmation !== 'CONFIRMED') return;
                if (filter === 'not' && c.confirmation === 'CONFIRMED') return;
                
                let isConf = c.confirmation === 'CONFIRMED';
                html += `
                    <div style="background:white; border-radius:10px; padding:12px; display:flex; align-items:center; gap:12px; border: 1px solid ${isConf ? '#10b981' : 'var(--border)'};">
                        <div style="width:28px; height:28px; border-radius:50%; background:#f1f5f9; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; color:var(--text-muted); flex-shrink:0;">${c.stop_number}</div>
                        <div style="flex:1; overflow:hidden;">
                            <div style="font-weight:600; font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${c.name} (Sr. ${c.id})</div>
                            <div style="font-size:12px; color:var(--text-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${c.address || 'No address'}</div>
                        </div>
                        <div style="flex-shrink:0;">
                            <label style="position:relative; display:inline-block; width:52px; height:28px;">
                                <input type="checkbox" ${isConf ? 'checked' : ''} onchange="toggleConf('${c.id}')" style="opacity:0; width:0; height:0;">
                                <span style="position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background-color:${isConf ? '#10b981' : '#cbd5e1'}; border-radius:28px; transition:.2s;">
                                    <span style="position:absolute; content:''; height:20px; width:20px; left:4px; bottom:4px; background-color:white; border-radius:50%; transition:.2s; transform:${isConf ? 'translateX(24px)' : 'translateX(0)'};"></span>
                                </span>
                            </label>
                        </div>
                    </div>
                `;
            });
            document.getElementById('conf-list').innerHTML = html;
        };
        
        window.saveConfirmationsAndAssign = async function() {
            let btn = document.getElementById('btn-conf-save');
            btn.disabled = true;
            let origText = btn.innerText;
            btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving...';
            
            let payload = {};
            Object.values(currentConfData).forEach(c => {
                payload[c.id] = c.confirmation;
            });
            
            let driverId = currentConfDriver;
            if (currentConfIsEditOnly) {
                // Find existing driver for this truck
                let driver = data.drivers.find(d => String(d.truck_id) === String(currentConfTruck));
                if (driver) driverId = driver.id;
            }
            
            try {
                let res = await fetch('/api/assign_driver', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        driver_id: driverId, 
                        truck_id: currentConfTruck,
                        confirmations: payload
                    })
                });
                let result = await res.json();
                if(result.success) {
                    if (result.firebase_synced === false) {
                        alert("Saved, but the driver app could not be updated (Firebase sync failed). Please try again.");
                    }
                    closeConfModal();
                    loadData();
                } else {
                    alert("Error: " + result.error);
                }
            } catch(e) {
                alert("An error occurred");
            }
            btn.disabled = false;
            btn.innerText = origText;
        };"""
content = content.replace(old_assign_js, new_assign_js)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS Step 5")
