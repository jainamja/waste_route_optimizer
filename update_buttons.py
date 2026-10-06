content = open('templates/live_dashboard.html', 'rb').read().decode('utf-8').replace('\r\n', '\n')

old_header = '''        <div style="display:flex; gap:12px; align-items:center;">
            <button onclick="openAddStopModal()" class="btn btn-primary" id="add-stop-btn" style="background:#10b981; border:none; display:none;"><i class="fa-solid fa-plus"></i> Add Stop</button>
            <a href="/live" class="btn btn-primary" target="_blank" style="text-decoration:none;"><i class="fa-solid fa-satellite-dish"></i> Open Live Tracking</a>
            <a href="/download_excel" class="btn btn-outline" id="export-btn" style="display:none; text-decoration:none;">
                <i class="fa-solid fa-file-excel"></i> Export Report
            </a>
            <button onclick="document.getElementById('add-driver-modal').style.display='flex'" class="btn" style="background:#8b5cf6; color:white; border:none; margin-left:8px;"><i class="fa-solid fa-user-plus"></i> Create Driver</button>
            <a href="/logout" class="btn" style="background:var(--border); color:var(--text-main); text-decoration:none; margin-left:8px;"><i class="fa-solid fa-arrow-right-from-bracket"></i> Logout</a>
        </div>'''

new_header = '''        <div style="display:flex; gap:12px; align-items:center;">
            <button onclick="openAddStopModal()" class="btn btn-primary" id="add-stop-btn" style="background:#10b981; border:none; display:none;"><i class="fa-solid fa-plus"></i> Add Stop</button>
            <a href="/live" class="btn btn-primary" target="_blank" style="text-decoration:none;"><i class="fa-solid fa-satellite-dish"></i> Open Live Tracking</a>
            <a href="/download_excel" class="btn btn-outline" id="export-btn" style="display:none; text-decoration:none;">
                <i class="fa-solid fa-file-excel"></i> Export Report
            </a>
            <a href="/" class="btn" style="background:var(--primary); color:white; border:none; margin-left:8px; text-decoration:none;"><i class="fa-solid fa-house"></i> Control Panel</a>
            <a href="/logout" class="btn" style="background:var(--border); color:var(--text-main); text-decoration:none; margin-left:8px;"><i class="fa-solid fa-arrow-right-from-bracket"></i> Logout</a>
        </div>'''

if old_header in content:
    content = content.replace(old_header, new_header)
    open('templates/live_dashboard.html', 'w', newline='\r\n', encoding='utf-8').write(content)
    print("SUCCESS")
else:
    print("NOT FOUND")
