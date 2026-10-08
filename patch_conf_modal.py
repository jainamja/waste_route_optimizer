import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

# For renderConfList
old_conf_arr = """            let arr = Object.values(currentConfData).sort((a,b) => (a.stop_number||999) - (b.stop_number||999));
            
            let confirmedCount = arr.filter(c => c.confirmation === 'CONFIRMED').length;
            let cancelledCount = arr.filter(c => c.confirmation === 'CANCELLED').length;
            let notCount = arr.length - confirmedCount - cancelledCount;
            document.getElementById('conf-counts').innerText = `${confirmedCount} confirmed \u00B7 ${notCount} not \u00B7 ${cancelledCount} cancelled`;
            
            let html = '';
            arr.forEach(c => {"""

new_conf_arr = """            let arr = Object.values(currentConfData).sort((a,b) => (a.stop_number||999) - (b.stop_number||999));
            
            let confirmedCount = arr.filter(c => c.confirmation === 'CONFIRMED').length;
            let cancelledCount = arr.filter(c => c.confirmation === 'CANCELLED').length;
            let notCount = arr.length - confirmedCount - cancelledCount;
            document.getElementById('conf-counts').innerText = `${confirmedCount} confirmed \u00B7 ${notCount} not \u00B7 ${cancelledCount} cancelled`;
            
            let html = '';
            let dynSr = 1;
            arr.forEach(c => {
                let currentSr = dynSr++;"""

text = text.replace(old_conf_arr, new_conf_arr)

old_conf_html = """                    <div style="background:white; border-radius:10px; padding:12px; display:flex; flex-direction:column; gap:12px; border: 1px solid ${borderColor};">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div style="width:28px; height:28px; border-radius:50%; background:#f1f5f9; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; color:var(--text-muted); flex-shrink:0;">${c.stop_number}</div>
                            <div style="flex:1; overflow:hidden;">
                                <div style="font-weight:600; font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-decoration:${isCanc ? 'line-through' : 'none'}; color:${isCanc ? 'var(--text-muted)' : 'var(--text-main)'};">${c.name} (Sr. ${c.id})</div>"""

new_conf_html = """                    <div style="background:white; border-radius:10px; padding:12px; display:flex; flex-direction:column; gap:12px; border: 1px solid ${borderColor};">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div style="width:28px; height:28px; border-radius:50%; background:#f1f5f9; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; color:var(--text-muted); flex-shrink:0;">${currentSr}</div>
                            <div style="flex:1; overflow:hidden;">
                                <div style="font-weight:600; font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-decoration:${isCanc ? 'line-through' : 'none'}; color:${isCanc ? 'var(--text-muted)' : 'var(--text-main)'};">${c.name}</div>"""

text = text.replace(old_conf_html, new_conf_html)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
