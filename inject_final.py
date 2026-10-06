import os

filepaths = ['templates/driver_view.html', 'src/index.html']

for filepath in filepaths:
    content = open(filepath, 'rb').read().decode('utf-8')
    content = content.replace('\\r\\n', '\\n')

    # 1. Update window.markStop
    start = content.find('        window.markStop = function(status) {')
    end = content.find('        window.openNavigation = function() {')
    
    if start != -1 and end != -1:
        new_markstop = """        window.markStop = function(status) {
            console.log("[MARK STOP] Tapped:", status, "| Current Index:", currentIndex);
            if (currentIndex < stops.length) {
                const stop = stops[currentIndex];
                
                if (status === 'SKIPPED' && stop.subStops && stop.subStops.length > 1) {
                    // Open Group Skip Modal
                    openGroupSkipModal(stop);
                    return;
                }
                
                let updates = {};
                if (stop.subStops) {
                    stop.subStops.forEach(ss => {
                        // Only mark as COMPLETED/SKIPPED if still PENDING
                        if (ss.status === 'PENDING') {
                            updates[ss.id + "/status"] = status;
                        }
                    });
                } else {
                    updates[stop.id + "/status"] = status;
                }
                
                db.ref(`routes/route_${truckId}/stops`).update(updates).catch(err => {
                    console.error("Firebase write failed (markStop):", err);
                    alert("Failed to update stop status. Check connection.");
                });
                
                snapSheet(snapPoints.peek);
            }
        };
        
        window.openGroupSkipModal = function(stop) {
            let pendingSubStops = stop.subStops.filter(ss => ss.status === 'PENDING');
            if (pendingSubStops.length === 0) return;
            
            let modalHtml = `
                <div id="groupSkipModalOverlay" class="modal-overlay" style="display:flex; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.5); z-index:9999; justify-content:center; align-items:flex-end;" onclick="if(event.target===this) closeGroupSkipModal()">
                    <div class="modal-content" style="background:var(--surface); width:100%; border-radius:24px 24px 0 0; padding:20px; box-shadow:0 -5px 20px rgba(0,0,0,0.1); max-height:80vh; overflow-y:auto; padding-bottom:max(20px, env(safe-area-inset-bottom));">
                        <h3 style="margin-top:0; margin-bottom:15px; font-size:18px;">Which stop to skip?</h3>
                        <div id="skipRadioGroup">
                            ${pendingSubStops.map(ss => `
                                <label style="display:flex; align-items:center; padding:15px; border:1px solid #e5e7eb; border-radius:12px; margin-bottom:10px; gap:15px;">
                                    <input type="radio" name="skipCustomerRadio" value="${ss.id}" onchange="document.getElementById('skipSelectedBtn').disabled = false" style="width:20px; height:20px;">
                                    <div style="flex:1;">
                                        <div style="font-weight:600; font-size:16px;">${ss.name} ${ss.id && ss.id > 0 ? `(Sr. ${ss.id})` : ''}</div>
                                        <div style="font-size:14px; color:var(--text-secondary); margin-top:4px;">${ss.address}</div>
                                    </div>
                                </label>
                            `).join('')}
                        </div>
                        
                        <div style="display:flex; flex-direction:column; gap:10px; margin-top:20px;">
                            <button id="skipSelectedBtn" class="btn btn-danger" disabled onclick="skipSelectedCustomer(event)" style="border-radius:12px; padding:15px; font-size:16px;">Skip selected customer</button>
                            <button class="btn" onclick="closeGroupSkipModal()" style="background:#f3f4f6; color:var(--text-primary); border-radius:12px; padding:15px; font-size:16px;">Cancel</button>
                            <a href="#" onclick="skipAllRemainingCustomers(event)" style="text-align:center; color:var(--text-secondary); margin-top:10px; font-size:14px; text-decoration:underline;">Skip all remaining at this location</a>
                        </div>
                    </div>
                </div>
            `;
            
            // Remove existing modal if any
            closeGroupSkipModal();
            document.body.insertAdjacentHTML('beforeend', modalHtml);
        };
        
        window.closeGroupSkipModal = function() {
            let existing = document.getElementById('groupSkipModalOverlay');
            if (existing) existing.remove();
        };
        
        window.skipSelectedCustomer = function(e) {
            e.preventDefault();
            if (e.target.disabled) return;
            e.target.disabled = true;
            
            let selected = document.querySelector('input[name="skipCustomerRadio"]:checked');
            if (!selected) return;
            
            let customerId = selected.value;
            let updates = {};
            updates[customerId + "/status"] = 'SKIPPED';
            
            db.ref(`routes/route_${truckId}/stops`).update(updates).then(() => {
                closeGroupSkipModal();
            }).catch(err => {
                console.error("Firebase write failed:", err);
                alert("Failed to update stop status.");
                e.target.disabled = false;
            });
        };
        
        window.skipAllRemainingCustomers = function(e) {
            e.preventDefault();
            const stop = stops[currentIndex];
            let updates = {};
            stop.subStops.forEach(ss => {
                if (ss.status === 'PENDING') {
                    updates[ss.id + "/status"] = 'SKIPPED';
                }
            });
            
            db.ref(`routes/route_${truckId}/stops`).update(updates).then(() => {
                closeGroupSkipModal();
                snapSheet(snapPoints.peek);
            }).catch(err => {
                console.error("Firebase write failed:", err);
                alert("Failed to update stop status.");
            });
        };

"""
        content = content[:start] + new_markstop + content[end:]

    # 2. Fix the grouping logic
    old_group = """                if (subStops.length > 1) {
                    s.subStops = subStops;
                    s.status = subStops[0].status; // fallback
                    // if any substop is pending, whole group is pending
                    if (subStops.some(ss => ss.status === 'PENDING')) {
                        s.status = 'PENDING';
                    }
                }"""
                
    new_group = """                if (subStops.length > 1) {
                    s.subStops = subStops;
                    let hasPending = subStops.some(ss => ss.status === 'PENDING');
                    let allSkipped = subStops.every(ss => ss.status === 'SKIPPED');
                    
                    if (hasPending) {
                        s.status = 'PENDING';
                    } else if (allSkipped) {
                        s.status = 'SKIPPED';
                    } else {
                        s.status = 'COMPLETED';
                    }
                }"""
    content = content.replace(old_group, new_group)

    # 3. Header logic
    old_header = """                    if (stop.subStops) {
                        subStopsHtml = `<div style="background:#eef2ff; color:#4f46e5; padding:10px 15px; border-radius:8px; margin:15px 0; font-size:14px; font-weight:600;">
                            <i class="fa-solid fa-layer-group"></i> ${stop.subStops.length} Customers at this Location
                        </div>`;
                    }"""
    new_header = """                    if (stop.subStops) {
                        let pendingCount = stop.subStops.filter(ss => ss.status === 'PENDING').length;
                        subStopsHtml = `<div style="background:#eef2ff; color:#4f46e5; padding:10px 15px; border-radius:8px; margin:15px 0; font-size:14px; font-weight:600;">
                            <i class="fa-solid fa-layer-group"></i> ${pendingCount} Customer${pendingCount !== 1 ? 's' : ''} remaining at this Location
                        </div>`;
                    }"""
    content = content.replace(old_header, new_header)

    # 4. Icon logic
    old_icon = """                let icon = '<i class="fa-regular fa-circle status-icon pending"></i>';
                let classes = 'stop-item';
                if (idx < currentIndex) {
                    icon = s.status === 'SKIPPED' ? '<i class="fa-solid fa-circle-xmark status-icon skipped"></i>' : '<i class="fa-solid fa-circle-check status-icon completed"></i>';
                    classes += ' completed';
                } else if (idx === currentIndex) {
                    icon = '<i class="fa-solid fa-location-dot status-icon" style="color:var(--primary);"></i>';
                    classes += ' active';
                }"""
                
    new_icon = """                let icon = '<i class="fa-regular fa-circle status-icon pending"></i>';
                let classes = 'stop-item';
                if (idx < currentIndex) {
                    if (s.status === 'SKIPPED') {
                        icon = '<i class="fa-solid fa-circle-xmark status-icon skipped"></i>';
                    } else if (s.subStops && s.subStops.some(ss => ss.status === 'SKIPPED') && s.subStops.some(ss => ss.status === 'COMPLETED')) {
                        icon = '<i class="fa-solid fa-circle-half-stroke status-icon" style="color:#f59e0b;"></i>';
                    } else {
                        icon = '<i class="fa-solid fa-circle-check status-icon completed"></i>';
                    }
                    classes += ' completed';
                } else if (idx === currentIndex) {
                    icon = '<i class="fa-solid fa-location-dot status-icon" style="color:var(--primary);"></i>';
                    classes += ' active';
                }"""
    content = content.replace(old_icon, new_icon)

    # 5. resetRoute
    old_reset = """                    stops.forEach(s => {
                        if (s.id > 0) {
                            updates[s.id + '/status'] = 'PENDING';
                        }
                    });"""
    new_reset = """                    stops.forEach(s => {
                        if (s.subStops) {
                            s.subStops.forEach(ss => {
                                if (ss.id > 0) updates[ss.id + '/status'] = 'PENDING';
                            });
                        } else if (s.id > 0) {
                            updates[s.id + '/status'] = 'PENDING';
                        }
                    });"""
    content = content.replace(old_reset, new_reset)

    # 6. Display Name
    old_display = """let displayName = isDepot ? s.name : `Stop ${s.sequence}: ${s.name}`;"""
    new_display = """let displayName = isDepot ? s.name : `Stop ${s.sequence} ${s.id && s.id > 0 ? `(Sr. ${s.id})` : ''}: ${s.name}`;
                if (s.subStops && s.status !== 'PENDING') {
                    let skippedCount = s.subStops.filter(ss => ss.status === 'SKIPPED').length;
                    let compCount = s.subStops.filter(ss => ss.status === 'COMPLETED').length;
                    if (skippedCount > 0) {
                        displayName += ` <span style="font-size:12px; color:#f59e0b; margin-left:5px;">(${skippedCount} skipped, ${compCount} completed)</span>`;
                    }
                }"""
    content = content.replace(old_display, new_display)

    # 7. Complete button
    old_btn = """<i class="fa-solid fa-check"></i> ${isLast ? 'Finish' : 'Complete & Next'}"""
    new_btn = """<i class="fa-solid fa-check"></i> ${isLast ? 'Finish' : (stop.subStops ? `Complete ${stop.subStops.filter(ss => ss.status === 'PENDING').length} & Next` : 'Complete & Next')}"""
    content = content.replace(old_btn, new_btn)

    open(filepath, 'w', newline='', encoding='utf-8').write(content)

print("SUCCESS")
