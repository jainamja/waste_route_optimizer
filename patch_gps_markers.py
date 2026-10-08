import io

with io.open('templates/live_tracking.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_gps_loop = """                for(let tId in trucks) {
                    let truck = trucks[tId];
                    if(truck.status === 'online' && truck.currentLat && truck.currentLng) {"""

new_gps_loop = """                for(let tId in trucks) {
                    let truck = trucks[tId];
                    
                    // Do not render GPS markers for phantom trucks
                    let hasRealRoute = false;
                    let routeNode = routesData['route_' + tId] || {};
                    let stopsObj = routeNode.stops || routeNode;
                    let stops = parseStops(stopsObj);
                    if (stops.filter(s => s.id > -1000 && s.name !== 'End Location / Depot').length > 0) hasRealRoute = true;
                    
                    if(hasRealRoute && truck.status === 'online' && truck.currentLat && truck.currentLng) {"""

text = text.replace(old_gps_loop, new_gps_loop)

# Also fix the fallback listener map marker creation
old_fallback_gps = """                            // Map update
                            if (tData.status === 'online' && tData.currentLat && tData.currentLng) {"""

new_fallback_gps = """                            // Map update
                            let hasRealRoute = false;
                            let routeNode = routesData['route_' + tId] || {};
                            let stopsObj = routeNode.stops || routeNode;
                            let stops = parseStops(stopsObj);
                            if (stops.filter(s => s.id > -1000 && s.name !== 'End Location / Depot').length > 0) hasRealRoute = true;

                            if (hasRealRoute && tData.status === 'online' && tData.currentLat && tData.currentLng) {"""

text = text.replace(old_fallback_gps, new_fallback_gps)

with io.open('templates/live_tracking.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
