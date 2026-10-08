import io

with io.open('src/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_updateGps = """            const updateGps = async () => {
                try {"""

new_updateGps = """            const updateGps = async () => {
                // If native plugin exists and is active, let native handle it.
                // If web fallback, we handle it here.
                if (!window.isTrackingActive) return;
                
                try {"""

text = text.replace(old_updateGps, new_updateGps)

old_endShift = """        window.endShift = function() {
            if(confirm("Are you sure you want to end your shift? This will clear your remaining stops.")) {
                db.ref(`routes/route_${window.currentTruckId}`).remove();
            }
        };"""

new_endShift = """        window.endShift = function() {
            if(confirm("Are you sure you want to end your shift? This will clear your remaining stops.")) {
                if (window.isTrackingActive) toggleTracking();
                db.ref(`routes/route_${window.currentTruckId}`).remove();
            }
        };"""

text = text.replace(old_endShift, new_endShift)

with io.open('src/index.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
