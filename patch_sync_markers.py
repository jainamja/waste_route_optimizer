import io

with io.open('templates/live_tracking.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_update = """        function updateMapPopups() {
            let trucks = window.liveTrucks || {};
            for(let tId in liveTruckMarkers) {
                let st = truckStats[tId];
                // Hide marker if truckStats not populated (i.e., truck has no route)
                if (!st) {
                    map.removeLayer(liveTruckMarkers[tId]);
                    delete liveTruckMarkers[tId];
                    continue;
                }
                let dName = driverMap[tId] || 'Unassigned';
                let countsStr = `<br><span style="font-size:12px; color:#64748b;">${st.comp} done &middot; ${st.left} left</span>`;
                liveTruckMarkers[tId].getPopup().setContent(`<b>Truck ${tId}</b> (${dName})<br>Live GPS${countsStr}`);
            }
        }"""

new_update = """        function updateMapPopups() {
            let trucks = window.liveTrucks || {};
            
            // Sync all active trucks that have real routes
            for(let tId in truckStats) {
                let truck = trucks[tId];
                if (truck && truck.status === 'online' && truck.currentLat && truck.currentLng) {
                    if (liveTruckMarkers[tId]) {
                        liveTruckMarkers[tId].setLatLng([truck.currentLat, truck.currentLng]);
                    } else {
                        let truckIcon = L.divIcon({
                            className: 'live-truck-icon',
                            html: `<div style='background-color:#2F5FFF; width:40px; height:40px; border-radius:50%; border:3px solid white; box-shadow:0 4px 10px rgba(0,0,0,0.4); display:flex; align-items:center; justify-content:center; color:white; font-size:18px;'><i class="fa-solid fa-truck"></i></div>`,
                            iconSize: [40, 40],
                            iconAnchor: [20, 20]
                        });
                        liveTruckMarkers[tId] = L.marker([truck.currentLat, truck.currentLng], {icon: truckIcon}).addTo(map);
                        liveTruckMarkers[tId].bindPopup("<b>Truck " + tId + "</b><br>Live GPS").openPopup();
                    }
                }
            }
            
            // Update popups and remove invalid markers
            for(let tId in liveTruckMarkers) {
                let st = truckStats[tId];
                let truck = trucks[tId];
                if (!st || !truck || truck.status !== 'online') {
                    map.removeLayer(liveTruckMarkers[tId]);
                    delete liveTruckMarkers[tId];
                    continue;
                }
                let dName = driverMap[tId] || 'Unassigned';
                let countsStr = `<br><span style="font-size:12px; color:#64748b;">${st.comp} done &middot; ${st.left} left</span>`;
                liveTruckMarkers[tId].getPopup().setContent(`<b>Truck ${tId}</b> (${dName})<br>Live GPS${countsStr}`);
            }
        }"""

text = text.replace(old_update, new_update)

with io.open('templates/live_tracking.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
