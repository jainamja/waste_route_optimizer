import io
import re

with io.open('src/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_toggle = """                // Start tracking
                if (window.Capacitor && window.Capacitor.Plugins.BackgroundLocation) {
                    try {
                        await window.Capacitor.Plugins.BackgroundLocation.start({"""

new_toggle = """                // Start tracking
                if (window.Capacitor && window.Capacitor.Plugins.BackgroundLocation) {
                    try {
                        // Request permissions first via Capacitor Geolocation
                        if (window.Capacitor.Plugins.Geolocation) {
                            await window.Capacitor.Plugins.Geolocation.requestPermissions();
                        }
                        await window.Capacitor.Plugins.BackgroundLocation.start({"""

text = text.replace(old_toggle, new_toggle)

with io.open('src/index.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
