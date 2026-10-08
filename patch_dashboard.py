import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_filter = '''<select id="conf-filter" onchange="renderConfList()" style="padding:10px; border:1px solid 
var(--border); border-radius:8px; font-family:'Inter',sans-serif; font-size:14px; background:white;">
                    <option value="all">All</option>
                    <option value="confirmed">Confirmed</option>
                    <option value="not">Not confirmed</option>
                </select>
                <button onclick="markAllConf()" class="btn btn-outline" style="padding:10px;"><i class="fa-solid 
fa-check-double"></i></button>'''

new_filter = '''<select id="conf-filter" onchange="renderConfList()" style="padding:10px; border:1px solid var(--border); border-radius:8px; font-family:'Inter',sans-serif; font-size:14px; background:white;">
                    <option value="all">All</option>
                    <option value="confirmed">Confirmed</option>
                    <option value="not">Not confirmed</option>
                    <option value="cancelled">Cancelled</option>
                </select>
                <button onclick="markAllConf()" title="Mark all confirmed" class="btn btn-outline" style="padding:10px;"><i class="fa-solid fa-check-double"></i></button>
                <button onclick="markAllNotConf()" title="Mark all not confirmed" class="btn btn-outline" style="padding:10px;"><i class="fa-solid fa-xmark"></i></button>'''

text = text.replace(old_filter.replace('\n', ''), new_filter) # fallback if whitespace issue
text = text.replace(
'''<select id="conf-filter" onchange="renderConfList()" style="padding:10px; border:1px solid var(--border); border-radius:8px; font-family:'Inter',sans-serif; font-size:14px; background:white;">
                    <option value="all">All</option>
                    <option value="confirmed">Confirmed</option>
                    <option value="not">Not confirmed</option>
                </select>
                <button onclick="markAllConf()" class="btn btn-outline" style="padding:10px;"><i class="fa-solid fa-check-double"></i></button>''', new_filter)

old_toggle = '''        window.toggleConf = function(id) {
            let c = currentConfData[id];
            c.confirmation = (c.confirmation === 'CONFIRMED') ? 'NOT_CONFIRMED' : 'CONFIRMED';
            renderConfList();
        };
        
        window.markAllConf = function() {
            Object.values(currentConfData).forEach(c => c.confirmation = 'CONFIRMED');
            renderConfList();
        };'''

new_toggle = '''        window.setConf = function(id, val) {
            let c = currentConfData[id];
            if (val === 'CANCELLED' && c.status === 'COMPLETED') return;
            c.confirmation = val;
            renderConfList();
        };
        
        window.markAllConf = function() {
            Object.values(currentConfData).forEach(c => c.confirmation = 'CONFIRMED');
            renderConfList();
        };
        
        window.markAllNotConf = function() {
            Object.values(currentConfData).forEach(c => c.confirmation = 'NOT_CONFIRMED');
            renderConfList();
        };'''

if old_toggle in text:
    text = text.replace(old_toggle, new_toggle)
else:
    print("Toggle not found")

old_render = '''        window.renderConfList = function() {
            let search = document.getElementById('conf-search').value.toLowerCase();
            let filter = document.getElementById('conf-filter').value;
            
            let arr = Object.values(currentConfData).sort((a,b) => (a.stop_number||999) - (b.stop_number||999));
            
            let confirmedCount = arr.filter(c => c.confirmation === 'CONFIRMED').length;
            let notCount = arr.length - confirmedCount;
            document.getElementById('conf-counts').innerText = `${confirmedCount} confirmed \u00B7 ${notCount} not`;
            
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
        };'''

new_render = '''        window.renderConfList = function() {
            let search = document.getElementById('conf-search').value.toLowerCase();
            let filter = document.getElementById('conf-filter').value;
            
            let arr = Object.values(currentConfData).sort((a,b) => (a.stop_number||999) - (b.stop_number||999));
            
            let confirmedCount = arr.filter(c => c.confirmation === 'CONFIRMED').length;
            let cancelledCount = arr.filter(c => c.confirmation === 'CANCELLED').length;
            let notCount = arr.length - confirmedCount - cancelledCount;
            document.getElementById('conf-counts').innerText = `${confirmedCount} confirmed \u00B7 ${notCount} not \u00B7 ${cancelledCount} cancelled`;
            
            let html = '';
            arr.forEach(c => {
                let match = c.name.toLowerCase().includes(search) || (c.address||'').toLowerCase().includes(search) || (c.phone||'').toLowerCase().includes(search);
                if (!match) return;
                
                let isConf = c.confirmation === 'CONFIRMED';
                let isCanc = c.confirmation === 'CANCELLED';
                let isNot = !isConf && !isCanc;
                
                if (filter === 'confirmed' && !isConf) return;
                if (filter === 'cancelled' && !isCanc) return;
                if (filter === 'not' && !isNot) return;
                
                let borderColor = isConf ? '#10b981' : (isCanc ? '#ef4444' : 'var(--border)');
                
                html += `
                    <div style="background:white; border-radius:10px; padding:12px; display:flex; flex-direction:column; gap:12px; border: 1px solid ${borderColor};">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div style="width:28px; height:28px; border-radius:50%; background:#f1f5f9; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; color:var(--text-muted); flex-shrink:0;">${c.stop_number}</div>
                            <div style="flex:1; overflow:hidden;">
                                <div style="font-weight:600; font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-decoration:${isCanc ? 'line-through' : 'none'}; color:${isCanc ? 'var(--text-muted)' : 'var(--text-main)'};">${c.name} (Sr. ${c.id})</div>
                                <div style="font-size:12px; color:var(--text-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${c.address || 'No address'}</div>
                            </div>
                        </div>
                        <div style="display:flex; border-radius:8px; overflow:hidden; border:1px solid var(--border);">
                            <button onclick="setConf('${c.id}', 'CONFIRMED')" style="flex:1; padding:10px 0; border:none; background:${isConf?'#10b981':'#f8fafc'}; color:${isConf?'white':'#64748b'}; font-size:13px; font-weight:600; cursor:pointer;">Confirmed</button>
                            <button onclick="setConf('${c.id}', 'NOT_CONFIRMED')" style="flex:1; padding:10px 0; border:none; border-left:1px solid var(--border); border-right:1px solid var(--border); background:${isNot?'#2F5FFF':'#f8fafc'}; color:${isNot?'white':'#64748b'}; font-size:13px; font-weight:600; cursor:pointer;">Not Confirmed</button>
                            <button onclick="setConf('${c.id}', 'CANCELLED')" ${c.status==='COMPLETED'?'disabled title="Already collected"':''} style="flex:1; padding:10px 0; border:none; background:${isCanc?'#ef4444':'#f8fafc'}; color:${isCanc?'white':'#64748b'}; font-size:13px; font-weight:600; cursor:${c.status==='COMPLETED'?'not-allowed':'pointer'}; opacity:${c.status==='COMPLETED'?'0.5':'1'};">Cancelled</button>
                        </div>
                    </div>
                `;
            });
            document.getElementById('conf-list').innerHTML = html;
        };'''

if old_render in text:
    text = text.replace(old_render, new_render)
else:
    print("Render not found")

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
