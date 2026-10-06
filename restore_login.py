import sys

def inject_login_overlay(filepath):
    content = open(filepath, 'rb').read().decode('utf-8').replace('\r\n', '\n')
    
    if '<div id="login-overlay">' in content:
        print(f"{filepath} already has login overlay")
        return

    overlay_html = """
    <!-- Login Overlay -->
    <div id="login-overlay">
        <svg class="splash-logo" viewBox="0 0 24 24" style="margin-bottom:20px; animation:none; transform:scale(1.15); opacity:1;">
            <path d="M20 8h-3V4c0-1.1-.9-2-2-2H5C3.9 2 3 2.9 3 4v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM8 16c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm10 0c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-3-11v6H5V5h10zm3.5 3l1.5 2h-3V8h1.5z"/>
        </svg>
        <div class="login-box">
            <h3 style="margin:0 0 8px 0;text-align:center;">Driver Login</h3>
            <p style="text-align:center;color:var(--text-muted);font-size:14px;margin-bottom:24px;">Enter your assigned mobile number to view your route</p>
            <input type="tel" id="username" placeholder="Mobile Number" autocomplete="tel">
            <input type="password" id="password" placeholder="Password">
            <div id="login-error" style="color:var(--red);font-size:13px;margin-bottom:12px;text-align:center;display:none;font-weight:600;"></div>
            <button id="login-btn" onclick="handleDriverLogin()">Sign In</button>
        </div>
    </div>
"""

    idx = content.find('<body>') + 6
    result = content[:idx] + overlay_html + content[idx:]
    
    # Also, we need to hide the login overlay in initApp if token IS found!
    # Wait, in the JS, if initApp is called on boot, it will show login if no token.
    # We should make sure `initApp()` shows it.
    
    # Check initApp
    initApp_idx = result.find('if (!token) {\n                document.getElementById(\'truck-title\').innerText = "Invalid Link";')
    if initApp_idx != -1:
        new_logic = '''if (!token) {
                document.getElementById('login-overlay').style.display = 'flex';
                return;
            }'''
        
        # Replace the invalid link block with showing the login screen
        old_logic = "if (!token) {\n                document.getElementById('truck-title').innerText = \"Invalid Link\";\n                document.getElementById('current-stop-container').innerHTML = `<div style=\"text-align:center; color:#e11d48; padding:20px;\"><b>Error:</b> Invalid or missing driver token.</div>`;\n                return;\n            }"
        result = result.replace(old_logic, new_logic)

    # And we must also hide the login overlay during successful init
    init_success = "document.getElementById('truck-title').innerText = \"Truck \" + truckId;"
    if init_success in result:
        result = result.replace(init_success, "document.getElementById('login-overlay').style.display = 'none';\n                " + init_success)

    open(filepath, 'w', newline='\r\n', encoding='utf-8').write(result)
    print(f"SUCCESS updated {filepath}")

inject_login_overlay('templates/driver_view.html')
inject_login_overlay('src/index.html')
