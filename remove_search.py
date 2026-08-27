import re

with open('templates/select_start_point.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove script from head
content = re.sub(r'<script src="https://maps\.googleapis\.com.*?"></script>\n', '', content)

# 2. Remove CSS styles
content = re.sub(r'\s*/\* Google Maps Search Bar Styles \*/.*?\.pac-item-query \{ color: #ffffff; font-weight: 600; \}', '', content, flags=re.DOTALL)

# 3. Revert Map HTML
search_html = '''                <div id="map" style="position: relative; margin-bottom: 15px; height: 350px;">
                    <div id="pac-container">
                        <input id="pac-input" type="text" placeholder="Search Google Maps...">
                    </div>
                </div>'''
content = content.replace(search_html, '                <div id="map" style="margin-bottom: 15px;"></div>')

# 4. Revert JavaScript
js_to_remove = '''        // Google Maps Places Autocomplete integration
        var input = document.getElementById('pac-input');
        if (typeof google !== 'undefined') {
            var autocomplete = new google.maps.places.Autocomplete(input);
            autocomplete.addListener('place_changed', function() {
                var place = autocomplete.getPlace();
                if (!place.geometry || !place.geometry.location) {
                    alert("No details available for input: '" + place.name + "'");
                    return;
                }
                
                var lat = place.geometry.location.lat();
                var lng = place.geometry.location.lng();
                var latlng = [lat, lng];
                
                map.setView(latlng, 15);
                
                if (startMarker) map.removeLayer(startMarker);
                startMarker = L.marker(latlng, {
                    icon: L.divIcon({className: 'custom-div-icon', html: '<div style="background-color:#3b82f6; width:16px; height:16px; border-radius:50%; border:3px solid #1c1c1e; box-shadow:0 2px 4px rgba(0,0,0,0.5);"></div>'})
                }).addTo(map).bindPopup("<b>Start Location:</b><br>" + place.name).openPopup();
                
                document.getElementById('start_lat').value = lat;
                document.getElementById('start_lng').value = lng;
            });
            
            // Prevent Enter key from submitting the form when selecting a place
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                }
            });
        } else {
            input.placeholder = "API Key required for search";
            input.disabled = true;
        }'''

content = content.replace(js_to_remove, '')

with open('templates/select_start_point.html', 'w', encoding='utf-8') as f:
    f.write(content)
