import io

with io.open('templates/live_tracking.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_popup = """                let countsStr = `<br><span style="font-size:12px; color:#64748b;">${st.comp} done &middot; ${st.left} left</span>`;
                liveTruckMarkers[tId].getPopup().setContent(`<b>Truck ${tId}</b> (${dName})<br>Live GPS${countsStr}`);"""

new_popup = """                let countsStr = `<br><span style="font-size:12px; color:#64748b;">${st.comp} done &middot; ${st.left} left</span>`;
                let timeStr = "Offline";
                if (truck.timestamp) {
                    let diffSeconds = Math.floor((Date.now() - truck.timestamp) / 1000);
                    if (diffSeconds < 15) timeStr = `<span style="color:#10b981;font-weight:700;">LIVE</span>`;
                    else if (diffSeconds < 60) timeStr = `LIVE (${diffSeconds}s ago)`;
                    else timeStr = `Updated ${Math.floor(diffSeconds/60)}m ago`;
                } else if (truck.status === 'online') {
                    timeStr = `<span style="color:#10b981;font-weight:700;">LIVE</span>`;
                }
                liveTruckMarkers[tId].getPopup().setContent(`<b>Truck ${tId}</b> (${dName})<br>${timeStr}${countsStr}`);"""

text = text.replace(old_popup, new_popup)

with io.open('templates/live_tracking.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
