import io

with io.open('src/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_logout = """        window.driverLogout = function() {
            if(confirm("Logout?")) {
                localStorage.removeItem('driver_token');"""

new_logout = """        window.driverLogout = function() {
            if(confirm("Logout?")) {
                if (window.isTrackingActive) toggleTracking();
                localStorage.removeItem('driver_token');"""

text = text.replace(old_logout, new_logout)

with io.open('src/index.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
