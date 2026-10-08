import io
import re

with io.open('src/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_navbar = """    <!-- Map -->
    <div id="navbar">
        <div class="navbar-title"><i class="fa-solid fa-truck"></i> <span id="truck-title">Loading...</span></div>
        <div style="display:flex; gap:16px; align-items:center;">
            <button onclick="resetRoute()" style="background:none; border:none; color:var(--text-muted); font-size:14px; font-weight:600; cursor:pointer;"><i class="fa-solid fa-rotate-right"></i></button>
            <button onclick="driverLogout()" style="background:var(--red); color:white; border:none; border-radius:8px; padding:6px 12px; font-size:14px; font-weight:700; cursor:pointer;"><i class="fa-solid fa-power-off"></i></button>
        </div>
    </div>"""

new_navbar = """    <!-- Map -->
    <div id="navbar">
        <div class="navbar-title"><i class="fa-solid fa-truck"></i> <span id="truck-title">Loading...</span></div>
        <div style="display:flex; gap:16px; align-items:center;">
            <button onclick="resetRoute()" style="background:none; border:none; color:var(--text-muted); font-size:14px; font-weight:600; cursor:pointer;"><i class="fa-solid fa-rotate-right"></i></button>
            <button onclick="driverLogout()" style="background:var(--red); color:white; border:none; border-radius:8px; padding:6px 12px; font-size:14px; font-weight:700; cursor:pointer;"><i class="fa-solid fa-power-off"></i></button>
        </div>
    </div>
    <div id="tracking-banner" style="display:none; padding:12px 16px; background:white; border-bottom:1px solid var(--border); align-items:center; justify-content:space-between; position:relative; z-index:900; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
        <div style="font-weight:700; font-size:13px; display:flex; align-items:center;" id="tracking-text">
            <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#94a3b8; margin-right:8px;" id="tracking-dot"></span>
            <span id="tracking-label" style="color:var(--text-main);">⚪ LOCATION NOT ACTIVE</span>
        </div>
        <button id="btn-tracking" onclick="toggleTracking()" style="background:var(--primary); color:white; border:none; padding:8px 16px; border-radius:8px; font-weight:700; font-size:13px; box-shadow:0 2px 6px rgba(47,95,255,0.3);">Start Route</button>
    </div>"""

text = text.replace(old_navbar, new_navbar)

old_login_succ = """                if (res.success) {
                    document.getElementById('login-screen').style.display = 'none';
                    setupTruckTracker(res.truck_id, res.token);
                } else {"""

new_login_succ = """                if (res.success) {
                    document.getElementById('login-screen').style.display = 'none';
                    window.currentTruckId = res.truck_id;
                    window.currentToken = res.token;
                    document.getElementById('tracking-banner').style.display = 'flex';
                    setupTruckTracker(res.truck_id, res.token);
                } else {"""

text = text.replace(old_login_succ, new_login_succ)

js_tracking = """        window.toggleTracking = async function() {
            if (window.isTrackingActive) {
                // Stop tracking
                if (window.Capacitor && window.Capacitor.Plugins.BackgroundLocation) {
                    await window.Capacitor.Plugins.BackgroundLocation.stop();
                }
                window.isTrackingActive = false;
                document.getElementById('tracking-dot').style.background = '#94a3b8';
                document.getElementById('tracking-label').innerText = '⚪ LOCATION NOT ACTIVE';
                document.getElementById('btn-tracking').innerText = 'Start Route';
                document.getElementById('btn-tracking').style.background = 'var(--primary)';
                if (window.currentTruckId) {
                    db.ref(`trucks/${window.currentTruckId}`).update({ status: 'offline' });
                }
            } else {
                // Start tracking
                if (window.Capacitor && window.Capacitor.Plugins.BackgroundLocation) {
                    try {
                        await window.Capacitor.Plugins.BackgroundLocation.start({
                            truckId: window.currentTruckId.toString(),
                            idToken: window.currentToken
                        });
                        window.isTrackingActive = true;
                        document.getElementById('tracking-dot').style.background = '#10b981';
                        document.getElementById('tracking-label').innerText = '🟢 LIVE LOCATION ACTIVE';
                        document.getElementById('btn-tracking').innerText = 'Stop';
                        document.getElementById('btn-tracking').style.background = 'var(--red)';
                    } catch(e) {
                        alert("Please grant Location permissions (Allow all the time if requested) to track your route in the background.");
                    }
                } else {
                    alert("Native background tracking not available in browser. Will use web fallback.");
                    window.isTrackingActive = true;
                    document.getElementById('tracking-dot').style.background = '#10b981';
                    document.getElementById('tracking-label').innerText = '🟢 LIVE LOCATION ACTIVE (WEB)';
                    document.getElementById('btn-tracking').innerText = 'Stop';
                    document.getElementById('btn-tracking').style.background = 'var(--red)';
                }
            }
        };"""

# Insert js_tracking before window.handleDriverLogin
text = text.replace("        window.handleDriverLogin = async function() {", js_tracking + "\n\n        window.handleDriverLogin = async function() {")

with io.open('src/index.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
