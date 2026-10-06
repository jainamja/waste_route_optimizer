content = open('templates/driver_view.html', 'rb').read().decode('utf-8').replace('\r\n', '\n')

splash_html = '''
    <!-- Splash Screen -->
    <div id="splash-screen">
        <svg class="splash-logo" viewBox="0 0 24 24">
            <path d="M20 8h-3V4c0-1.1-.9-2-2-2H5C3.9 2 3 2.9 3 4v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM8 16c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm10 0c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-3-11v6H5V5h10zm3.5 3l1.5 2h-3V8h1.5z"/>
        </svg>
    </div>
'''

if 'id="splash-screen"' not in content:
    idx = content.find('<body>') + 6
    content = content[:idx] + splash_html + content[idx:]

fade_script = '''
        // Hide splash screen after animation completes
        window.addEventListener('load', () => {
            setTimeout(() => {
                let splash = document.getElementById('splash-screen');
                if (splash) {
                    splash.style.opacity = '0';
                    setTimeout(() => splash.remove(), 400);
                }
            }, 2500); // 2.5 seconds (gives time for 2s animation + delay)
        });
'''
if 'splash.remove()' not in content:
    idx = content.rfind('</script>')
    content = content[:idx] + fade_script + content[idx:]

open('templates/driver_view.html', 'w', newline='\r\n', encoding='utf-8').write(content)
print("SUCCESS templates/driver_view.html")
