/**
 * MISSION CONTROL CORE SCRIPT
 * Handles theme toggling, toast notifications, command palette, and UI helpers.
 */

// Theme Management
function updateThemeIcons() {
    const isLight = document.documentElement.classList.contains('light');
    document.querySelectorAll('.theme-toggle-btn').forEach(btn => {
        btn.innerHTML = isLight 
            ? '<i data-lucide="moon" style="width: 16px; height: 16px;"></i>' 
            : '<i data-lucide="sun" style="width: 16px; height: 16px;"></i>';
        btn.title = isLight ? 'Switch to Dark Mode (Mission Control)' : 'Switch to Light Mode';
    });
    if (window.lucide) window.lucide.createIcons();
}

(function initTheme() {
    const savedTheme = localStorage.getItem('onroute_theme') || 'dark';
    if (savedTheme === 'light') {
        document.documentElement.classList.add('light');
        document.documentElement.classList.remove('dark');
    } else {
        document.documentElement.classList.add('dark');
        document.documentElement.classList.remove('light');
    }
    document.addEventListener('DOMContentLoaded', updateThemeIcons);
})();

function toggleTheme() {
    const isLight = document.documentElement.classList.toggle('light');
    document.documentElement.classList.toggle('dark', !isLight);
    localStorage.setItem('onroute_theme', isLight ? 'light' : 'dark');
    updateThemeIcons();
}

// Toast Notifications System (Replaces raw alert)
function showToast(message, type = 'info', duration = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `mission-toast ${type}`;
    
    let iconName = 'info';
    if (type === 'success') iconName = 'check-circle';
    if (type === 'error') iconName = 'alert-triangle';
    if (type === 'warning') iconName = 'alert-circle';

    toast.innerHTML = `
        <i data-lucide="${iconName}" style="width: 18px; height: 18px; flex-shrink: 0;"></i>
        <div style="flex: 1; word-break: break-word;">${message}</div>
    `;

    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px) scale(0.95)';
        setTimeout(() => toast.remove(), 250);
    }, duration);
}

// Custom Confirm Dialog
function showConfirm(title, message, onConfirm) {
    const modalId = 'mission-confirm-modal';
    let modal = document.getElementById(modalId);
    if (!modal) {
        modal = document.createElement('div');
        modal.id = modalId;
        modal.style.cssText = 'display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); backdrop-filter:blur(8px); z-index:100000; align-items:center; justify-content:center; padding:16px;';
        modal.innerHTML = `
            <div class="glass-card" style="max-width:440px; width:100%; padding:28px; background:var(--bg-surface-elevated); border:1px solid var(--border-glass);">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                    <div style="width:38px; height:38px; border-radius:10px; background:rgba(239,68,68,0.15); color:#ef4444; display:flex; align-items:center; justify-content:center;">
                        <i data-lucide="alert-triangle" style="width:20px; height:20px;"></i>
                    </div>
                    <h3 id="confirm-title" style="margin:0; font-size:18px; font-weight:700;">Confirm Action</h3>
                </div>
                <p id="confirm-message" style="color:var(--text-secondary); font-size:14px; line-height:1.5; margin:0 0 24px 0;"></p>
                <div style="display:flex; justify-content:flex-end; gap:12px;">
                    <button id="confirm-cancel-btn" class="btn-control btn-secondary">Cancel</button>
                    <button id="confirm-ok-btn" class="btn-control btn-danger">Confirm</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    document.getElementById('confirm-title').innerText = title;
    document.getElementById('confirm-message').innerText = message;
    modal.style.display = 'flex';
    if (window.lucide) window.lucide.createIcons();

    const okBtn = document.getElementById('confirm-ok-btn');
    const cancelBtn = document.getElementById('confirm-cancel-btn');

    okBtn.onclick = () => {
        modal.style.display = 'none';
        if (typeof onConfirm === 'function') onConfirm();
    };
    cancelBtn.onclick = () => {
        modal.style.display = 'none';
    };
}

// Global Command Palette (Ctrl+K / Cmd+K)
(function initCommandPalette() {
    window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            toggleCommandPalette();
        }
    });
})();

function toggleCommandPalette() {
    let cp = document.getElementById('cmd-palette');
    if (!cp) {
        cp = document.createElement('div');
        cp.id = 'cmd-palette';
        cp.style.cssText = 'display:none; position:fixed; inset:0; background:rgba(0,0,0,0.75); backdrop-filter:blur(8px); z-index:99999; align-items:flex-start; justify-content:center; padding-top:15vh;';
        cp.innerHTML = `
            <div class="glass-card" style="width:100%; max-width:540px; background:var(--bg-surface-elevated); border:1px solid var(--border-glass); box-shadow:0 25px 50px -12px rgba(0,0,0,0.5); overflow:hidden;">
                <div style="display:flex; align-items:center; gap:12px; padding:16px 20px; border-bottom:1px solid var(--border-glass);">
                    <i data-lucide="search" style="color:var(--text-muted); width:20px; height:20px;"></i>
                    <input id="cmd-input" type="text" placeholder="Type a destination or shortcut..." style="flex:1; background:transparent; border:none; outline:none; color:var(--text-primary); font-size:16px; font-family:inherit;">
                    <kbd style="background:rgba(255,255,255,0.08); border-radius:6px; padding:2px 8px; font-size:12px; color:var(--text-muted);">ESC</kbd>
                </div>
                <div id="cmd-results" style="padding:10px; display:flex; flex-direction:column; gap:4px; max-height:360px; overflow-y:auto;">
                    <a href="/dashboard" class="cmd-item" style="display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; color:var(--text-primary); text-decoration:none; transition:all 0.15s;">
                        <i data-lucide="layout-dashboard" style="width:18px; height:18px; color:var(--accent-primary);"></i>
                        <span style="font-weight:600; flex:1;">Admin Control Panel</span>
                        <span style="font-size:12px; color:var(--text-muted);">/dashboard</span>
                    </a>
                    <a href="/routes" class="cmd-item" style="display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; color:var(--text-primary); text-decoration:none; transition:all 0.15s;">
                        <i data-lucide="map" style="width:18px; height:18px; color:#38bdf8;"></i>
                        <span style="font-weight:600; flex:1;">Route Dashboard</span>
                        <span style="font-size:12px; color:var(--text-muted);">/routes</span>
                    </a>
                    <a href="/generate" class="cmd-item" style="display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; color:var(--text-primary); text-decoration:none; transition:all 0.15s;">
                        <i data-lucide="route" style="width:18px; height:18px; color:#a855f7;"></i>
                        <span style="font-weight:600; flex:1;">Generate New Routes</span>
                        <span style="font-size:12px; color:var(--text-muted);">/generate</span>
                    </a>
                    <a href="/live" class="cmd-item" style="display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; color:var(--text-primary); text-decoration:none; transition:all 0.15s;">
                        <i data-lucide="radio" style="width:18px; height:18px; color:#f59e0b;"></i>
                        <span style="font-weight:600; flex:1;">Live Fleet Tracking</span>
                        <span style="font-size:12px; color:var(--text-muted);">/live</span>
                    </a>
                    <div style="height:1px; background:var(--border-glass); margin:4px 0;"></div>
                    <button onclick="toggleTheme()" class="cmd-item" style="background:none; border:none; text-align:left; cursor:pointer; width:100%; display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; color:var(--text-primary); transition:all 0.15s;">
                        <i data-lucide="sun-moon" style="width:18px; height:18px; color:#eab308;"></i>
                        <span style="font-weight:600; flex:1;">Toggle Dark / Light Theme</span>
                        <span style="font-size:12px; color:var(--text-muted);">Theme</span>
                    </button>
                    <a href="/logout" class="cmd-item" style="display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; color:#ef4444; text-decoration:none; transition:all 0.15s;">
                        <i data-lucide="log-out" style="width:18px; height:18px;"></i>
                        <span style="font-weight:600; flex:1;">Sign Out</span>
                        <span style="font-size:12px; color:var(--text-muted);">/logout</span>
                    </a>
                </div>
            </div>
        `;
        document.body.appendChild(cp);

        // Click outside or ESC to close
        cp.addEventListener('click', (e) => {
            if (e.target === cp) cp.style.display = 'none';
        });
        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && cp.style.display === 'flex') cp.style.display = 'none';
        });

        // Hover effect on cmd items
        const items = cp.querySelectorAll('.cmd-item');
        items.forEach(el => {
            el.addEventListener('mouseenter', () => el.style.background = 'rgba(255,255,255,0.06)');
            el.addEventListener('mouseleave', () => el.style.background = 'transparent');
        });
    }

    if (cp.style.display === 'flex') {
        cp.style.display = 'none';
    } else {
        cp.style.display = 'flex';
        const input = document.getElementById('cmd-input');
        if (input) {
            input.value = '';
            input.focus();
        }
        if (window.lucide) window.lucide.createIcons();
    }
}

// Auto-run lucide on load
document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) window.lucide.createIcons();
});
