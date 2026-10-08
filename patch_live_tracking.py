import io
import re

with io.open('templates/live_tracking.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_loop = """            let cardsHtml = '';
            let tIds = Array.from(activeTruckIds).sort((a,b) => parseInt(a)-parseInt(b));
            
            tIds.forEach(tId => {
                if (!tId || tId === 'undefined' || isNaN(parseInt(tId))) return;
                
                let dName = driverMap[tId] || 'Truck ' + tId;
                let isOnline = trucks[tId] && trucks[tId].status === 'online';
                
                let routeNode = routesData['route_' + tId] || {};
                let stopsObj = routeNode.stops || routeNode;
                let stops = parseStops(stopsObj);
                console.log(`Truck ${tId}: parsed ${stops.length} stops from object:`, JSON.stringify(stopsObj).substring(0, 200));
                
                let tTotal = stops.length;
                let tComp = 0, tSkip = 0, tCanc = 0, tLeft = 0, tNotConf = 0;"""

new_loop = """            let cardsHtml = '';
            let tIds = Array.from(activeTruckIds).sort((a,b) => parseInt(a)-parseInt(b));
            
            // To properly track markers, we should know which ones are valid
            let validTruckIds = new Set();
            
            tIds.forEach(tId => {
                if (!tId || tId === 'undefined' || isNaN(parseInt(tId))) return;
                
                let routeNode = routesData['route_' + tId] || {};
                let stopsObj = routeNode.stops || routeNode;
                let stops = parseStops(stopsObj);
                
                // CRITICAL FILTER: Must have real customer stops!
                let realStops = stops.filter(s => s.id > -1000 && s.name !== 'End Location / Depot');
                if (realStops.length === 0) return;
                
                validTruckIds.add(tId.toString());
                
                let dName = driverMap[tId];
                if (!dName) dName = 'Unassigned';
                
                let isOnline = trucks[tId] && trucks[tId].status === 'online';
                
                console.log(`Truck ${tId}: parsed ${stops.length} stops from object:`, JSON.stringify(stopsObj).substring(0, 200));
                
                let tTotal = realStops.length;
                let tComp = 0, tSkip = 0, tCanc = 0, tLeft = 0, tNotConf = 0;"""

text = text.replace(old_loop, new_loop)

# I should also fix the map markers!
old_map_update = """        function updateMapPopups() {
            let trucks = window.liveTrucks || {};
            for(let tId in liveTruckMarkers) {
                let dName = driverMap[tId] || '';
                let st = truckStats[tId];
                let countsStr = st ? `<br><span style="font-size:12px; color:#64748b;">${st.comp} done &middot; ${st.left} left</span>` : '';
                liveTruckMarkers[tId].getPopup().setContent(`<b>Truck ${tId}</b> ${dName ? `(${dName})` : ''}<br>Live GPS${countsStr}`);
            }
        }"""

new_map_update = """        function updateMapPopups() {
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

text = text.replace(old_map_update, new_map_update)

with io.open('templates/live_tracking.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
