import os

filepath = 'templates/live_dashboard.html'
content = open(filepath, 'r', encoding='utf-8').read()

# 1. Add the save-template-btn
old_export_btn = """            <a href="/download_excel" class="btn btn-outline" id="export-btn" style="display:none; text-decoration:none;">
                <i class="fa-solid fa-file-excel"></i> Export Report
            </a>"""

new_btns = """            <button onclick="document.getElementById('save-template-modal').style.display='flex'" class="btn btn-outline" id="save-template-btn" style="display:none;">
                <i class="fa-solid fa-bookmark"></i> Save as Template
            </button>
            <a href="/download_excel" class="btn btn-outline" id="export-btn" style="display:none; text-decoration:none;">
                <i class="fa-solid fa-file-excel"></i> Export Report
            </a>"""

content = content.replace(old_export_btn, new_btns)

# 2. Add helper in loadData() and change the logic
old_loaddata = """        function loadData() {
            fetch('/api/data')
                .then(res => res.json())
                .then(resData => {
                    if (resData.error || !resData.routes || resData.routes.length === 0) {
                        document.getElementById('empty-state').style.display = 'block';
                        document.getElementById('dashboard-content').style.display = 'none';
                        document.getElementById('live-indicator').style.display = 'none';
                        document.getElementById('export-btn').style.display = 'none';
                        document.getElementById('add-stop-btn').style.display = 'none';
                        document.getElementById('save-template-btn').style.display = 'none';
                        return;
                    }
                    data = resData;
                    document.getElementById('empty-state').style.display = 'none';
                    document.getElementById('dashboard-content').style.display = 'flex';
                    document.getElementById('live-indicator').style.display = 'flex';
                    document.getElementById('export-btn').style.display = 'inline-flex';
                    document.getElementById('add-stop-btn').style.display = 'inline-flex';
                    document.getElementById('save-template-btn').style.display = 'inline-flex';
                    
                    updateHeaderStats();
                    renderMap();
                    renderSidebar();
                })
                .catch(err => {
                    console.error("Failed to load routes:", err);
                    document.getElementById('empty-state').style.display = 'block';
                });
        }"""

new_loaddata = """        function loadData() {
            const setDisplay = (id, val) => {
                let el = document.getElementById(id);
                if (el) el.style.display = val;
            };

            fetch('/api/data')
                .then(res => res.json())
                .then(resData => {
                    if (resData.error || !resData.routes || resData.routes.length === 0) {
                        setDisplay('empty-state', 'block');
                        setDisplay('error-state', 'none');
                        setDisplay('dashboard-content', 'none');
                        setDisplay('live-indicator', 'none');
                        setDisplay('export-btn', 'none');
                        setDisplay('add-stop-btn', 'none');
                        setDisplay('save-template-btn', 'none');
                        return;
                    }
                    data = resData;
                    setDisplay('empty-state', 'none');
                    setDisplay('error-state', 'none');
                    setDisplay('dashboard-content', 'flex');
                    setDisplay('live-indicator', 'flex');
                    setDisplay('export-btn', 'inline-flex');
                    setDisplay('add-stop-btn', 'inline-flex');
                    setDisplay('save-template-btn', 'inline-flex');
                    
                    updateHeaderStats();
                    renderMap();
                    renderSidebar();
                })
                .catch(err => {
                    console.error("Failed to load routes:", err);
                    setDisplay('empty-state', 'none');
                    setDisplay('dashboard-content', 'none');
                    
                    let errorState = document.getElementById('error-state');
                    if (errorState) {
                        errorState.style.display = 'block';
                        document.getElementById('error-msg').innerText = String(err);
                    }
                });
        }"""
        
content = content.replace(old_loaddata, new_loaddata)

# 3. Add error state html below empty state
old_empty_state = """    <div id="empty-state" class="empty-state" style="display: none;">
        <i class="fa-solid fa-map-location-dot"></i>
        <h2 class="heading">No Routes Active</h2>
        <p>You haven't generated any optimized routes yet. Please return to the Setup page to configure your fleet and upload your stops.</p>
        <a href="/" class="btn btn-primary">Go to Setup</a>
    </div>"""

new_error_state = old_empty_state + """

    <div id="error-state" class="empty-state" style="display: none;">
        <i class="fa-solid fa-triangle-exclamation" style="color: var(--danger);"></i>
        <h2 class="heading">Failed to load routes</h2>
        <p id="error-msg" style="color: var(--danger);"></p>
        <button onclick="loadData()" class="btn btn-primary">Retry</button>
    </div>"""

content = content.replace(old_empty_state, new_error_state)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS")
