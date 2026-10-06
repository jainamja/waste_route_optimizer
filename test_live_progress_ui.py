import os
import json
import pytest
from playwright.sync_api import sync_playwright

def test_live_progress_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        html_path = os.path.join(os.path.dirname(__file__), 'templates', 'live_tracking.html')
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        def create_page(is_mobile=False):
            if is_mobile:
                context = browser.new_context(viewport={'width': 375, 'height': 812})
            else:
                context = browser.new_context()
            page = context.new_page()
            page.on('console', lambda msg: print(f"BROWSER: {msg.text}"))
            
            def handle_route(route, request):
                url = request.url
                if 'leaflet' in url or 'font-awesome' in url or 'fonts.googleapis' in url or 'firebase' in url:
                    route.fulfill(status=200, body='')
                elif '/api/data' in url:
                    route.fulfill(status=200, json={
                        "drivers": [
                            {"truck_id": "1", "name": "Driver Bob"},
                            {"truck_id": "2", "name": "Driver Alice"},
                            {"truck_id": "3", "name": "Driver Charlie"}
                        ]
                    })
                elif url == 'http://localhost:5000/live':
                    route.fulfill(status=200, body=html_content, content_type='text/html')
                else:
                    route.fulfill(status=200, body='')
            
            page.route('**/*', handle_route)
            
            page.add_init_script('''
                window.fakeSnapshots = {};
                window.firebaseRefs = {};
                
                window.firebase = {
                    initializeApp: function() {},
                    auth: function() {
                        return { signInAnonymously: function() { return Promise.resolve(); } };
                    },
                    database: function() {
                        return {
                            ref: function(path) {
                                if (!window.firebaseRefs[path]) {
                                    window.firebaseRefs[path] = {
                                        callbacks: [],
                                        on: function(event, cb, errCb) {
                                            if (event === 'value') {
                                                this.callbacks.push({cb: cb, errCb: errCb});
                                                if (window.fakeSnapshots[path] !== undefined) {
                                                    cb({ val: () => window.fakeSnapshots[path] });
                                                }
                                            }
                                        },
                                        trigger: function(val) {
                                            window.fakeSnapshots[path] = val;
                                            this.callbacks.forEach(c => c.cb({ val: () => val }));
                                        },
                                        triggerError: function(err) {
                                            this.callbacks.forEach(c => { if(c.errCb) c.errCb(err); });
                                        }
                                    };
                                }
                                return window.firebaseRefs[path];
                            }
                        };
                    }
                };
                
                window.L = {
                    map: function() { return { setView: function() { return this; }, fitBounds: function(){}, removeLayer: function(){}, flyTo: function(){} }; },
                    tileLayer: function() { return { addTo: function() {} }; },
                    latLngBounds: function() { return { extend: function() {} }; },
                    divIcon: function() { return {}; },
                    marker: function() { return { addTo: function(){ return this; }, bindPopup: function(){ return this; }, openPopup: function(){}, getPopup: function(){ return { setContent: function(){} }; } }; }
                };
                
                window.pushSnapshot = function(path, data) {
                    firebase.database().ref(path).trigger(data);
                };
            ''')
            
            page.goto('http://localhost:5000/live')
            page.wait_for_timeout(500)
            return page

        page = create_page(False)
        
        trucks_data = {
            "1": { "status": "online", "currentLat": 10, "currentLng": 10 },
            "2": { "status": "online", "currentLat": 20, "currentLng": 20 },
            "3": { "status": "offline" }
        }
        
        routes_data = {
            "route_1": {
                "stops": {
                    "101": { "id": 101, "status": "COMPLETED", "sequence": 1 },
                    "102": { "id": 102, "status": "PENDING", "sequence": 2 },
                    "-1001": { "id": -1001, "name": "End Location / Depot" }
                }
            },
            "route_2": [
                None,
                { "id": 201, "status": "COMPLETED", "sequence": 1 },
                { "id": 202, "status": "SKIPPED", "sequence": 2 },
                { "id": 203, "status": "PENDING", "sequence": 3 },
                { "id": -1002, "name": "End Location / Depot" }
            ],
            "route_3": {}
        }
        
        page.evaluate('window.pushSnapshot("trucks", %s)' % json.dumps(trucks_data))
        page.evaluate('window.pushSnapshot("routes", %s)' % json.dumps(routes_data))
        page.wait_for_timeout(500)
        
        t1_stats = page.locator('.t-card').filter(has_text='Truck 1').locator('.t-stats').inner_text()
        assert '1 done' in t1_stats
        assert '0 skipped' in t1_stats
        assert '1 left' in t1_stats
        
        t2_stats = page.locator('.t-card').filter(has_text='Truck 2').locator('.t-stats').inner_text()
        assert '1 done' in t2_stats
        assert '1 skipped' in t2_stats
        assert '1 left' in t2_stats
        
        t3_stats = page.locator('.t-card').filter(has_text='Truck 3').locator('.t-stats').inner_text()
        assert 'Waiting for routes' in t3_stats or 'No stops' in t3_stats
        
        fleet_vals = page.locator('.fleet-stat-val').all_inner_texts()
        assert '2' in fleet_vals # done
        assert '1' in fleet_vals # skip
        
        routes_data['route_1']['stops']['102']['status'] = 'COMPLETED'
        page.evaluate('window.pushSnapshot("routes", %s)' % json.dumps(routes_data))
        page.wait_for_timeout(300)
        
        t1_stats = page.locator('.t-card').filter(has_text='Truck 1').locator('.t-stats').inner_text()
        assert '2 done' in t1_stats
        assert '0 left' in t1_stats
        
        page.screenshot(path='desktop.png')
        
        page_mobile = create_page(True)
        page_mobile.evaluate('window.pushSnapshot("trucks", %s)' % json.dumps(trucks_data))
        page_mobile.evaluate('window.pushSnapshot("routes", %s)' % json.dumps(routes_data))
        page_mobile.wait_for_timeout(500)
        
        panel = page_mobile.locator('.progress-panel')
        assert 'collapsed' in panel.get_attribute('class')
        
        page_mobile.locator('.panel-header').click()
        page_mobile.wait_for_timeout(300)
        assert 'collapsed' not in panel.get_attribute('class')
        
        page_mobile.screenshot(path='mobile.png')
        
        browser.close()
        print("ALL TESTS PASSED")

if __name__ == '__main__':
    test_live_progress_ui()
