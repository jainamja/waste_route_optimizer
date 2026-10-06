import sys

def fix_error_handling(filepath):
    content = open(filepath, 'rb').read().decode('utf-8').replace('\r\n', '\n')
    
    old = '''                document.getElementById('truck-title').innerText = "Error";
                document.getElementById('current-stop-container').innerHTML = `<div style="text-align:center; color:#e11d48; padding:20px;"><b>This route has ended</b><br>Please ask dispatch for a new link.</div>`;'''
                
    new = '''                document.getElementById('login-overlay').style.display = 'flex';
                let err = document.getElementById('login-error');
                err.innerText = "Session expired or invalid route. Please log in again.";
                err.style.display = 'block';'''
                
    if old in content:
        result = content.replace(old, new)
        open(filepath, 'w', newline='\r\n', encoding='utf-8').write(result)
        print(f"SUCCESS updated {filepath}")
    else:
        print(f"NOT FOUND in {filepath}")

fix_error_handling('templates/driver_view.html')
fix_error_handling('src/index.html')
