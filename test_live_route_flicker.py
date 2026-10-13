import sys
import os
import json
import time
import math
import argparse
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

SCRATCH_DIR = r"C:\Users\Jainam\.gemini\antigravity\brain\8fc11bef-cbbd-47f1-9b7c-c51607ec392f\scratch"
LEAFLET_JS_PATH = os.path.join(SCRATCH_DIR, "node_modules", "leaflet", "dist", "leaflet.js")
LEAFLET_CSS_PATH = os.path.join(SCRATCH_DIR, "node_modules", "leaflet", "dist", "leaflet.css")

# 1x1 transparent PNG for mocked map tiles
TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

FAKE_FIREBASE_JS = r"""
(function() {
    if (window.firebase && window.firebase.__isFake) return;
    const listeners = {};
    const currentData = {
        driver_locations: {},
        trucks: {},
        routes: {}
    };

    function getByPath(path) {
        const parts = String(path || '').split('/').filter(Boolean);
        let cur = currentData;
        for (const p of parts) {
            if (cur == null || typeof cur !== 'object') return null;
            cur = cur[p];
        }
        return cur !== undefined ? JSON.parse(JSON.stringify(cur)) : null;
    }

    function setByPath(path, val) {
        const parts = String(path || '').split('/').filter(Boolean);
        if (parts.length === 0) return;
        let cur = currentData;
        for (let i = 0; i < parts.length - 1; i++) {
            if (!cur[parts[i]] || typeof cur[parts[i]] !== 'object') {
                cur[parts[i]] = {};
            }
            cur = cur[parts[i]];
        }
        cur[parts[parts.length - 1]] = JSON.parse(JSON.stringify(val));
    }

    function notifyPath(changedPath) {
        const cleanChanged = String(changedPath || '').replace(/^\/+|\/+$/g, '');
        Object.keys(listeners).forEach(regPath => {
            if (regPath === cleanChanged || regPath.startsWith(cleanChanged + '/') || cleanChanged.startsWith(regPath + '/')) {
                const val = getByPath(regPath);
                const snap = { val: () => val };
                (listeners[regPath] || []).forEach(cb => {
                    try { cb(snap); } catch (e) { console.error(e); }
                });
            }
        });
    }

    window.__pushFirebase = function(path, val) {
        const clean = String(path || '').replace(/^\/+|\/+$/g, '');
        setByPath(clean, val);
        notifyPath(clean);
    };

    window.firebase = {
        __isFake: true,
        initializeApp: function() {},
        auth: function() {
            return {
                signInAnonymously: function() {
                    return Promise.resolve({ user: { uid: 'fake-admin-uid' } });
                }
            };
        },
        database: function() {
            return {
                ref: function(path) {
                    const clean = String(path || '').replace(/^\/+|\/+$/g, '');
                    return {
                        on: function(eventType, cb, errCb) {
                            if (eventType !== 'value') return;
                            if (!listeners[clean]) listeners[clean] = [];
                            listeners[clean].push(cb);
                            setTimeout(() => {
                                const val = getByPath(clean);
                                if (val !== null && Object.keys(val).length > 0) {
                                    cb({ val: () => val });
                                }
                            }, 5);
                        }
                    };
                }
            };
        }
    };
})();
"""

OBSERVER_INIT_JS = r"""
window.__initOverlayObserver = function() {
    const pane = document.querySelector('.leaflet-overlay-pane');
    window.__obs = {
        firstRoadDrawn: false,
        monitoring: true,
        zeroRoadMoments: 0,
        dashedAppearances: 0,
        lastHadZeroRoad: false,
        lastHadDashed: false,
        sampleCount: 0,
        missingRoadFrames: 0
    };

    function inspectDom() {
        if (!pane) return { solidCount: 0, dashedCount: 0 };
        const paths = Array.from(pane.querySelectorAll('path'));
        let solidCount = 0;
        let dashedCount = 0;
        for (const p of paths) {
            const d = p.getAttribute('d') || '';
            if (d.length <= 2) continue;
            const dash = p.getAttribute('stroke-dasharray');
            if (dash && dash.trim().length > 0) {
                dashedCount++;
            } else {
                solidCount++;
            }
        }
        if (solidCount > 0 && dashedCount === 0 && !window.__obs.firstRoadDrawn) {
            window.__obs.firstRoadDrawn = true;
        }
        if (window.__obs.firstRoadDrawn && window.__obs.monitoring) {
            if (solidCount === 0) {
                if (!window.__obs.lastHadZeroRoad) {
                    window.__obs.zeroRoadMoments++;
                    window.__obs.lastHadZeroRoad = true;
                }
            } else {
                window.__obs.lastHadZeroRoad = false;
            }
            if (dashedCount > 0) {
                if (!window.__obs.lastHadDashed) {
                    window.__obs.dashedAppearances++;
                    window.__obs.lastHadDashed = true;
                }
            } else {
                window.__obs.lastHadDashed = false;
            }
        }
        return { solidCount, dashedCount };
    }

    window.__inspectOverlay = inspectDom;
    window.__resetObserverCounters = function() {
        const cur = inspectDom();
        window.__obs.zeroRoadMoments = 0;
        window.__obs.dashedAppearances = 0;
        window.__obs.lastHadZeroRoad = (cur.solidCount === 0);
        window.__obs.lastHadDashed = (cur.dashedCount > 0);
        window.__obs.sampleCount = 0;
        window.__obs.missingRoadFrames = 0;
    };

    if (pane) {
        if (window.__activeMutationObserver) {
            window.__activeMutationObserver.disconnect();
        }
        const mo = new MutationObserver(() => {
            inspectDom();
        });
        mo.observe(pane, { childList: true, subtree: true, attributes: true, attributeFilter: ['d', 'stroke-dasharray', 'stroke'] });
        window.__activeMutationObserver = mo;
    }
    if (window.__activePollInterval) {
        clearInterval(window.__activePollInterval);
    }
    window.__activePollInterval = setInterval(inspectDom, 50);
};
"""


def make_initial_stops():
    return {
        "1": {
            "id": 1,
            "name": "Customer Alpha",
            "address": "101 Nehru Bridge West",
            "phone": "9876543210",
            "lat": 23.022629,
            "lng": 72.573063,
            "sequence": 1,
            "status": "PENDING",
            "confirmation": "CONFIRMED"
        },
        "2": {
            "id": 2,
            "name": "Customer Beta",
            "address": "202 Lal Darwaja",
            "phone": "9876543211",
            "lat": 23.022191,
            "lng": 72.579062,
            "sequence": 2,
            "status": "PENDING",
            "confirmation": "NOT_CONFIRMED"
        },
        "3": {
            "id": 3,
            "name": "Customer Gamma",
            "address": "303 Rustom Cama Marg",
            "phone": "9876543212",
            "lat": 23.025034,
            "lng": 72.580450,
            "sequence": 3,
            "status": "PENDING",
            "confirmation": "CONFIRMED"
        },
        "4": {
            "id": 4,
            "name": "Customer Delta",
            "address": "404 Mirzapur Road",
            "phone": "9876543213",
            "lat": 23.028968,
            "lng": 72.585251,
            "sequence": 4,
            "status": "PENDING",
            "confirmation": "CONFIRMED"
        },
        "-1001": {
            "id": -1001,
            "name": "End Location / Depot",
            "address": "Main Municipal Depot",
            "phone": "",
            "lat": 23.031321,
            "lng": 72.586262,
            "sequence": 5,
            "status": "PENDING",
            "confirmation": "CONFIRMED"
        }
    }


REAL_ROAD_ANCHORS = [
    (72.571448, 23.022548),
    (72.573063, 23.022629),
    (72.579062, 23.022191),
    (72.580450, 23.025034),
    (72.585251, 23.028968),
    (72.586262, 23.031321),
]

REAL_OSRM_LEGS = {
    (0, 1): [[72.571442, 23.022548], [72.571442, 23.02254], [72.571436, 23.022343], [72.571312, 23.022314], [72.57128, 23.022565], [72.571315, 23.022605], [72.57136, 23.022636], [72.571438, 23.022677], [72.571754, 23.022689], [72.571782, 23.022688], [72.572173, 23.02267], [72.573063, 23.022629]],
    (1, 2): [[72.573063, 23.022629], [72.573297, 23.022614], [72.573557, 23.022591], [72.577411, 23.02236], [72.577708, 23.022306], [72.578025, 23.022196], [72.578062, 23.022189], [72.578239, 23.022158], [72.578926, 23.022186], [72.579062, 23.022191]],
    (2, 3): [[72.579062, 23.022191], [72.579303, 23.022193], [72.57954, 23.022149], [72.579549, 23.022233], [72.579539, 23.022801], [72.579531, 23.023008], [72.579498, 23.02318], [72.57939, 23.023404], [72.579299, 23.023453], [72.579177, 23.023445], [72.579028, 23.023454], [72.578998, 23.023523], [72.579047, 23.023863], [72.579046, 23.024001], [72.579046, 23.024076], [72.579045, 23.024206], [72.579045, 23.024246], [72.579041, 23.025029], [72.579546, 23.025029], [72.579663, 23.025018], [72.579743, 23.02501], [72.579789, 23.025005], [72.579966, 23.024987], [72.580241, 23.024974], [72.580337, 23.024984], [72.580387, 23.025002], [72.58045, 23.025034]],
    (3, 4): [[72.58045, 23.025034], [72.58058, 23.025101], [72.580599, 23.026507], [72.580627, 23.026631], [72.580622, 23.026853], [72.580622, 23.02703], [72.580652, 23.027093], [72.580679, 23.027162], [72.580714, 23.027213], [72.580759, 23.027258], [72.580812, 23.027294], [72.580871, 23.02732], [72.580982, 23.027341], [72.581112, 23.027372], [72.581218, 23.027432], [72.581291, 23.027505], [72.581351, 23.027615], [72.581355, 23.027745], [72.581371, 23.027891], [72.58139, 23.028074], [72.581405, 23.028127], [72.581436, 23.028243], [72.581484, 23.028418], [72.581573, 23.028745], [72.58168, 23.028926], [72.582019, 23.029092], [72.58227, 23.029237], [72.582383, 23.029555], [72.582408, 23.029586], [72.582491, 23.029685], [72.58267, 23.029839], [72.582908, 23.029521], [72.583078, 23.029312], [72.583167, 23.029246], [72.58331, 23.029183], [72.583563, 23.029075], [72.583937, 23.028956], [72.584451, 23.028921], [72.584709, 23.028909], [72.584882, 23.028789], [72.585239, 23.028962], [72.585251, 23.028968]],
    (4, 5): [[72.585251, 23.028968], [72.585286, 23.029049], [72.585608, 23.029795], [72.585695, 23.030004], [72.585835, 23.03034], [72.58598, 23.030771], [72.585987, 23.030796], [72.586009, 23.030855], [72.586106, 23.031082], [72.586262, 23.031321]],
}


def _match_anchor_idx(pt):
    for idx, (alng, alat) in enumerate(REAL_ROAD_ANCHORS):
        if abs(pt[0] - alng) < 0.0025 and abs(pt[1] - alat) < 0.0025:
            return idx
    return None


def build_osrm_geometry_from_url(url_str):
    path_part = url_str.split("/route/v1/driving/")[-1].split("?")[0]
    path_part = unquote(path_part)
    raw_pts = [p for p in path_part.split(";") if "," in p]
    coords = []
    for p in raw_pts:
        lng_s, lat_s = p.split(",")[:2]
        coords.append([float(lng_s), float(lat_s)])

    dense_coords = []
    for i in range(len(coords)):
        if i == 0:
            dense_coords.append(coords[0])
        if i < len(coords) - 1:
            idx_a = _match_anchor_idx(coords[i])
            idx_b = _match_anchor_idx(coords[i + 1])
            if idx_a is not None and idx_b is not None and idx_a < idx_b:
                for step in range(idx_a, idx_b):
                    leg_pts = REAL_OSRM_LEGS.get((step, step + 1), [])
                    for pt in leg_pts[1:-1]:
                        dense_coords.append(pt)
                    if step + 1 < idx_b and leg_pts:
                        dense_coords.append(leg_pts[-1])
                dense_coords.append(coords[i + 1])
            else:
                mid_lng = round((coords[i][0] + coords[i + 1][0]) / 2.0 + 0.0001, 6)
                mid_lat = round((coords[i][1] + coords[i + 1][1]) / 2.0 - 0.0001, 6)
                dense_coords.append([mid_lng, mid_lat])
                dense_coords.append(coords[i + 1])
    return coords, {
        "code": "Ok",
        "routes": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": dense_coords
                },
                "distance": 1500.0,
                "duration": 180.0
            }
        ]
    }


def setup_mock_routes(page, html_path, osrm_state, allow_tiles=False):
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    with open(LEAFLET_JS_PATH, "r", encoding="utf-8") as f:
        leaflet_js = f.read()
    with open(LEAFLET_CSS_PATH, "r", encoding="utf-8") as f:
        leaflet_css = f.read()

    # SAFETY RULE: Block all real Firebase hosts unconditionally
    def block_firebase(route):
        url = route.request.url
        if "gstatic.com/firebasejs" in url:
            route.fulfill(status=200, content_type="application/javascript", body=FAKE_FIREBASE_JS)
        else:
            route.abort()

    page.route("**/*firebaseio.com/**", block_firebase)
    page.route("**/*identitytoolkit.googleapis.com/**", block_firebase)
    page.route("**/*gstatic.com/firebasejs/**", block_firebase)

    # Serve Leaflet locally
    page.route("**/leaflet.js*", lambda route: route.fulfill(status=200, content_type="application/javascript", body=leaflet_js))
    page.route("**/leaflet.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=leaflet_css))

    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logo.jpg")
    logo_bytes = open(logo_path, "rb").read() if os.path.exists(logo_path) else TRANSPARENT_PNG
    page.route("**/static/logo.jpg*", lambda route: route.fulfill(status=200, content_type="image/jpeg", body=logo_bytes))

    if not allow_tiles:
        # Block external fonts / icons / map tiles cleanly in offline mode
        page.route("**/*.google.com/vt/**", lambda route: route.fulfill(status=200, content_type="image/png", body=TRANSPARENT_PNG))
        page.route("**/fonts.googleapis.com/**", lambda route: route.fulfill(status=200, content_type="text/css", body=""))
        page.route("**/fonts.gstatic.com/**", lambda route: route.fulfill(status=200, content_type="font/woff2", body=b""))
        page.route("**/cdnjs.cloudflare.com/**", lambda route: route.fulfill(status=200, content_type="text/css", body=""))

    # Mock /api/data
    def handle_api_data(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "drivers": [
                    {"id": 101, "username": "driver1", "name": "Ramesh Kumar", "truck_id": 1},
                    {"id": 102, "username": "driver2", "name": "Suresh Patel", "truck_id": 2}
                ]
            })
        )

    page.route("**/api/data*", handle_api_data)

    # Mock OSRM with concurrency tracking, configurable delay, and configurable HTTP status
    def handle_osrm(route):
        now = time.time()
        url = route.request.url
        raw_coords, payload = build_osrm_geometry_from_url(url)
        osrm_state["in_flight"] += 1
        if osrm_state["in_flight"] > osrm_state["max_concurrent"]:
            osrm_state["max_concurrent"] = osrm_state["in_flight"]

        req_record = {
            "url": url,
            "timestamp": now,
            "num_waypoints": len(raw_coords),
            "first_pt": raw_coords[0] if raw_coords else None,
            "last_pt": raw_coords[-1] if raw_coords else None,
            "status": osrm_state["status"]
        }
        osrm_state["requests"].append(req_record)

        delay_ms = osrm_state.get("delay_ms", 40)
        if delay_ms > 0:
            # Note: inside Playwright sync handler we can't block the event loop with time.sleep if we want concurrent requests,
            # so we fulfill immediately unless delay is handled in page fetch wrapper or small sleep
            pass

        status_code = osrm_state.get("status", 200)
        osrm_state["in_flight"] -= 1
        if status_code != 200:
            route.fulfill(status=status_code, content_type="application/json", body=json.dumps({"message": "Too Many Requests"}))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("https://router.project-osrm.org/**", handle_osrm)

    # Serve the target HTML page at http://localhost.test/live
    page.route("http://localhost.test/live*", lambda route: route.fulfill(status=200, content_type="text/html", body=html_content))


# Install an in-page fetch wrapper that supports configurable async OSRM delay and concurrency measurement without blocking Playwright's single-threaded Python route callback
IN_PAGE_OSRM_SHIM = r"""
(function() {
    const origFetch = window.fetch.bind(window);
    window.__osrmMockConfig = {
        delayMs: 60,
        status: 200,
        inFlight: 0,
        maxConcurrent: 0,
        requests: []
    };
    window.fetch = async function(input, init) {
        const url = typeof input === 'string' ? input : (input && input.url ? input.url : String(input));
        if (url.includes('router.project-osrm.org')) {
            const cfg = window.__osrmMockConfig;
            cfg.inFlight++;
            if (cfg.inFlight > cfg.maxConcurrent) {
                cfg.maxConcurrent = cfg.inFlight;
            }
            const ts = performance.now();
            const pathPart = decodeURIComponent(url.split('/route/v1/driving/')[1].split('?')[0]);
            const pts = pathPart.split(';').filter(Boolean).map(p => p.split(',').map(Number));
            cfg.requests.push({
                url: url,
                timestampMs: ts,
                numWaypoints: pts.length,
                firstPt: pts[0],
                lastPt: pts[pts.length - 1],
                status: cfg.status
            });
            try {
                if (cfg.delayMs > 0) {
                    await new Promise((resolve, reject) => {
                        const t = setTimeout(resolve, cfg.delayMs);
                        if (init && init.signal) {
                            init.signal.addEventListener('abort', () => {
                                clearTimeout(t);
                                reject(new DOMException('Aborted', 'AbortError'));
                            });
                        }
                    });
                }
                if (cfg.status !== 200) {
                    return new Response(JSON.stringify({ message: 'Mock HTTP ' + cfg.status }), {
                        status: cfg.status,
                        headers: { 'Content-Type': 'application/json' }
                    });
                }
                return await origFetch(input, init);
            } finally {
                cfg.inFlight--;
            }
        }
        return origFetch(input, init);
    };
})();
"""


def run_test_suite(html_path, run_60s_jitter=True, record_video_name=None):
    results = {}
    console_errors = []
    page_errors = []
    osrm_state = {"requests": [], "in_flight": 0, "max_concurrent": 0, "delay_ms": 0, "status": 200}

    video_dir = os.path.join(SCRATCH_DIR, "videos")
    os.makedirs(video_dir, exist_ok=True)

    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium"
        browser = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)

        context_kwargs = {"viewport": {"width": 1280, "height": 800}}
        if record_video_name:
            context_kwargs["record_video_dir"] = video_dir
            context_kwargs["record_video_size"] = {"width": 1280, "height": 800}

        context = browser.new_context(**context_kwargs)
        context.add_init_script(IN_PAGE_OSRM_SHIM)
        page = context.new_page()

        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        setup_mock_routes(page, html_path, osrm_state, allow_tiles=bool(record_video_name))
        page.goto("http://localhost.test/live", wait_until="domcontentloaded")
        if record_video_name:
            page.wait_for_timeout(1200)
        page.evaluate(OBSERVER_INIT_JS)
        page.evaluate("window.__initOverlayObserver()")

        # Push initial truck & route data
        # Position truck at 23.022548, 72.571448 (right on .toFixed(4) boundary so 3-6m jitter crosses 23.0225 <-> 23.0226)
        base_lat = 23.022548
        base_lng = 72.571448
        initial_stops = make_initial_stops()

        page.evaluate(
            """([lat, lng, stops]) => {
                window.__pushFirebase('trucks', {
                    '1': { truckId: 1, driverName: 'Ramesh Kumar', currentLat: lat, currentLng: lng, status: 'online', lastUpdated: Date.now() }
                });
                window.__pushFirebase('routes', {
                    'route_1': { stops: stops }
                });
            }""",
            [base_lat, base_lng, initial_stops]
        )

        page.wait_for_timeout(350)

        # Capture Fleet Progress panel text for regression comparison (with done, skipped, cancelled, left, percent, Last Completed, Upcoming)
        reg_stops = make_initial_stops()
        reg_stops["1"]["status"] = "COMPLETED"
        reg_stops["2"]["status"] = "SKIPPED"
        reg_stops["3"]["confirmation"] = "CANCELLED"
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", reg_stops)
        page.wait_for_timeout(300)

        fleet_progress_snapshot = page.evaluate("""() => {
            return {
                summaryText: document.getElementById('fleet-summary').innerText.replace(/\\s+/g, ' ').trim(),
                truckCardText: document.getElementById('truck-list').innerText.replace(/\\s+/g, ' ').trim(),
                hasVTag: Boolean(document.getElementById('v-tag'))
            };
        }""")
        expected_summary = "1 DONE 1 SKIP 1 CANC 1 LEFT 25% PROGRESS"
        expected_card_substr = "1 done · 1 skipped · 1 cancelled · 1 left LAST COMPLETED Customer Alpha UPCOMING Customer Delta #4"
        results["fleet_progress"] = {
            "pass": (
                fleet_progress_snapshot["summaryText"].upper() == expected_summary
                and expected_card_substr.upper() in fleet_progress_snapshot["truckCardText"].upper()
                and "TRUCK 2" not in fleet_progress_snapshot["truckCardText"].upper()
            ),
            "summaryText": fleet_progress_snapshot["summaryText"],
            "truckCardText": fleet_progress_snapshot["truckCardText"],
            "unassigned_hidden": "TRUCK 2" not in fleet_progress_snapshot["truckCardText"].upper(),
            "hasVTag": fleet_progress_snapshot["hasVTag"]
        }

        # Restore initial 4 pending stops for route flicker tests
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", initial_stops)
        page.wait_for_timeout(300)

        # Turn on Truck 1's route
        page.evaluate("window.__osrmMockConfig.delayMs = 180;")
        page.evaluate("toggleTruckRoute('1', true);")

        # Wait for first road geometry draw
        for _ in range(40):
            obs = page.evaluate("window.__inspectOverlay(); window.__obs")
            if obs["firstRoadDrawn"]:
                break
            page.wait_for_timeout(100)

        page.wait_for_timeout(300)
        page.evaluate("window.__resetObserverCounters()")
        fetches_before_jitter = page.evaluate("window.__osrmMockConfig.requests.length")

        # =========================================================================
        # TEST (a): Stationary truck, GPS jitter of 2-8 m every second for 60 s
        # =========================================================================
        if run_60s_jitter:
            # Pre-computed deterministic 2-8m jitter offsets in degrees (~0.000025 to 0.000060 deg = 2.8m to 6.6m)
            for sec in range(60):
                sign = 1 if (sec % 2 == 0) else -1
                dlat = sign * (0.000025 + (sec % 4) * 0.000008)
                dlng = -sign * (0.000025 + (sec % 3) * 0.000008)
                j_lat = base_lat + dlat
                j_lng = base_lng + dlng
                page.evaluate(
                    """([lat, lng]) => {
                        window.__pushFirebase('trucks', {
                            '1': { truckId: 1, driverName: 'Ramesh Kumar', currentLat: lat, currentLng: lng, status: 'online', lastUpdated: Date.now() }
                        });
                    }""",
                    [j_lat, j_lng]
                )
                # Sample 10 times at 100ms intervals (= 1.0s per step, 600 samples across 60s)
                for sub in range(10):
                    page.wait_for_timeout(100)
                    page.evaluate("""() => {
                        const st = window.__inspectOverlay();
                        window.__obs.sampleCount++;
                        if (st.solidCount === 0) {
                            window.__obs.missingRoadFrames++;
                        }
                    }""")

            obs_after_a = page.evaluate("window.__obs")
            fetches_after_jitter = page.evaluate("window.__osrmMockConfig.requests.length")
            osrm_fetches_during_jitter = fetches_after_jitter - fetches_before_jitter

            # Take a screenshot at the end of the 60s jitter run in scratch
            screenshot_name = f"jitter60_{os.path.basename(html_path)}.png"
            page.screenshot(path=os.path.join(SCRATCH_DIR, screenshot_name))

            test_a_pass = (
                osrm_fetches_during_jitter == 0
                and obs_after_a["zeroRoadMoments"] == 0
                and obs_after_a["dashedAppearances"] == 0
                and obs_after_a["missingRoadFrames"] == 0
            )
            results["test_a"] = {
                "pass": test_a_pass,
                "osrm_fetches_after_first_draw": osrm_fetches_during_jitter,
                "zero_road_moments": obs_after_a["zeroRoadMoments"],
                "dashed_appearances": obs_after_a["dashedAppearances"],
                "missing_road_frames": obs_after_a["missingRoadFrames"],
                "total_samples": obs_after_a["sampleCount"]
            }

        # =========================================================================
        # TEST (b): OSRM mock delayed 3 s: completing a stop does NOT make line disappear
        # =========================================================================
        page.evaluate("window.__resetObserverCounters()")
        page.evaluate("window.__osrmMockConfig.delayMs = 3000;")
        stops_b = make_initial_stops()
        stops_b["1"]["status"] = "COMPLETED"
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_b)

        # Poll every 100ms for 3.5 seconds while OSRM is delayed 3s
        min_solid_during_b = 999
        max_dashed_during_b = 0
        for _ in range(35):
            page.wait_for_timeout(100)
            st = page.evaluate("window.__inspectOverlay()")
            if st["solidCount"] < min_solid_during_b:
                min_solid_during_b = st["solidCount"]
            if st["dashedCount"] > max_dashed_during_b:
                max_dashed_during_b = st["dashedCount"]

        obs_b = page.evaluate("window.__obs")
        test_b_pass = (min_solid_during_b >= 1 and max_dashed_during_b == 0 and obs_b["zeroRoadMoments"] == 0 and obs_b["dashedAppearances"] == 0)
        results["test_b"] = {
            "pass": test_b_pass,
            "min_solid_paths_during_3s_delay": min_solid_during_b,
            "max_dashed_paths_during_3s_delay": max_dashed_during_b,
            "zero_road_moments": obs_b["zeroRoadMoments"],
            "dashed_appearances": obs_b["dashedAppearances"]
        }

        # =========================================================================
        # TEST (c): Completing, skipping, and cancelling a stop each cause 1 stops-path refetch
        # =========================================================================
        page.evaluate("window.__osrmMockConfig.delayMs = 30;")
        page.wait_for_timeout(200)

        # Reset to 4 pending stops first and let it settle
        stops_c = make_initial_stops()
        # Nudge coordinates slightly so it's uncached for fresh count
        for k in ["1", "2", "3", "4"]:
            stops_c[k]["lat"] += 0.0002
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_c)
        page.wait_for_timeout(400)

        # 1) Complete stop 1
        c0 = page.evaluate("window.__osrmMockConfig.requests.length")
        stops_c["1"]["status"] = "COMPLETED"
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_c)
        page.wait_for_timeout(400)
        c1 = page.evaluate("window.__osrmMockConfig.requests.length")
        comp_fetches = c1 - c0

        # 2) Skip stop 2
        stops_c["2"]["status"] = "SKIPPED"
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_c)
        page.wait_for_timeout(400)
        c2 = page.evaluate("window.__osrmMockConfig.requests.length")
        skip_fetches = c2 - c1

        # 3) Cancel stop 3
        stops_c["3"]["confirmation"] = "CANCELLED"
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_c)
        page.wait_for_timeout(400)
        c3 = page.evaluate("window.__osrmMockConfig.requests.length")
        canc_fetches = c3 - c2

        results["test_c"] = {
            "pass": (comp_fetches == 1 and skip_fetches == 1 and canc_fetches == 1),
            "complete_fetches": comp_fetches,
            "skip_fetches": skip_fetches,
            "cancel_fetches": canc_fetches
        }

        # =========================================================================
        # TEST (d): A truck moving 200 m causes at most one approach-leg fetch per 10 s
        # =========================================================================
        stops_d = make_initial_stops()
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_d)
        page.wait_for_timeout(400)
        # Ensure 10s cooldown from initial approach fetch has expired by backdating lastApproachFetchTime by 10.5s
        page.evaluate("""() => {
            if (typeof activeRouteLayers !== 'undefined' && activeRouteLayers['1']) {
                activeRouteLayers['1'].lastApproachFetchTime = Date.now() - 10500;
            }
        }""")
        req_before_d = page.evaluate("window.__osrmMockConfig.requests.length")
        # Move truck 200m in 5 steps of 40m (~0.00036 deg per step) over 2.5 seconds
        for step in range(1, 6):
            m_lat = base_lat + step * 0.00036
            m_lng = base_lng + step * 0.00036
            page.evaluate(
                """([lat, lng]) => {
                    window.__pushFirebase('trucks', {
                        '1': { truckId: 1, driverName: 'Ramesh Kumar', currentLat: lat, currentLng: lng, status: 'online', lastUpdated: Date.now() }
                    });
                }""",
                [m_lat, m_lng]
            )
            page.wait_for_timeout(400)

        reqs_d = page.evaluate(f"window.__osrmMockConfig.requests.slice({req_before_d})")
        approach_fetches_d = len([r for r in reqs_d if r["numWaypoints"] == 2])
        stops_fetches_d = len([r for r in reqs_d if r["numWaypoints"] > 2])
        results["test_d"] = {
            "pass": (1 <= len(reqs_d) <= 1 and approach_fetches_d == 1 and stops_fetches_d == 0),
            "total_fetches_in_10s": len(reqs_d),
            "approach_fetches_in_10s": approach_fetches_d,
            "stops_fetches_in_10s": stops_fetches_d
        }

        # =========================================================================
        # TEST (e): 120 pending stops produce at least 3 chunked requests, merged line reaches last stop
        # =========================================================================
        stops_120 = {}
        last_stop_lat = 23.0250 + 119 * 0.001
        last_stop_lng = 72.5750 + 119 * 0.001
        for i in range(1, 121):
            stops_120[str(i)] = {
                "id": i,
                "name": f"Stop #{i}",
                "address": f"Addr {i}",
                "phone": "9000000000",
                "lat": round(23.0250 + (i - 1) * 0.001, 6),
                "lng": round(72.5750 + (i - 1) * 0.001, 6),
                "sequence": i,
                "status": "PENDING",
                "confirmation": "CONFIRMED"
            }

        req_before_e = page.evaluate("window.__osrmMockConfig.requests.length")
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_120)
        page.wait_for_timeout(800)
        reqs_e = page.evaluate(f"window.__osrmMockConfig.requests.slice({req_before_e})")

        # Check rendered line last coordinate on map
        last_rendered_coord = page.evaluate("""() => {
            const st = activeRouteLayers['1'];
            if (!st) return null;
            const layer = st.stopsLine || (st.lines && st.lines[st.lines.length - 1]);
            if (!layer || !layer.toGeoJSON) return null;
            const gj = layer.toGeoJSON();
            const feat = gj.features ? gj.features[0] : gj;
            if (!feat || !feat.geometry || !feat.geometry.coordinates) return null;
            const coords = feat.geometry.coordinates;
            return coords[coords.length - 1]; // [lng, lat]
        }""")

        reaches_last_stop = False
        if last_rendered_coord and len(last_rendered_coord) >= 2:
            reaches_last_stop = (
                abs(last_rendered_coord[1] - last_stop_lat) < 1e-4
                and abs(last_rendered_coord[0] - last_stop_lng) < 1e-4
            )

        results["test_e"] = {
            "pass": (len(reqs_e) >= 3 and reaches_last_stop),
            "chunk_requests_count": len(reqs_e),
            "last_rendered_coord": last_rendered_coord,
            "expected_last_stop": [round(last_stop_lng, 6), round(last_stop_lat, 6)],
            "reaches_last_stop": reaches_last_stop
        }

        # =========================================================================
        # TEST (f): OSRM returning 429: last good line stays on screen, retries follow backoff (2s, 4s, 8s)
        # =========================================================================
        page.evaluate("window.__resetObserverCounters()")
        page.evaluate("window.__osrmMockConfig.status = 429; window.__osrmMockConfig.delayMs = 10;")
        req_before_f = page.evaluate("window.__osrmMockConfig.requests.length")

        stops_f = make_initial_stops()
        for k in ["1", "2", "3", "4"]:
            stops_f[k]["lat"] += 0.0009  # uncached signature
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_f)

        # Wait 14.6 seconds to capture initial request (t=0), retry 1 (+2s), retry 2 (+4s), retry 3 (+8s)
        page.wait_for_timeout(14600)
        reqs_f = page.evaluate(f"window.__osrmMockConfig.requests.slice({req_before_f})")
        obs_f = page.evaluate("window.__obs")
        st_f = page.evaluate("window.__inspectOverlay()")

        # Restore status 200 and clear retry timer
        page.evaluate("window.__osrmMockConfig.status = 200;")
        page.wait_for_timeout(200)

        if len(reqs_f) >= 4:
            interval_1 = round((reqs_f[1]["timestampMs"] - reqs_f[0]["timestampMs"]) / 1000.0, 2)
            interval_2 = round((reqs_f[2]["timestampMs"] - reqs_f[1]["timestampMs"]) / 1000.0, 2)
            interval_3 = round((reqs_f[3]["timestampMs"] - reqs_f[2]["timestampMs"]) / 1000.0, 2)
        else:
            interval_1 = -1
            interval_2 = -1
            interval_3 = -1

        backoff_ok = (len(reqs_f) >= 4 and 1.6 <= interval_1 <= 2.6 and 3.5 <= interval_2 <= 4.7 and 7.4 <= interval_3 <= 8.8)
        line_stayed_f = (st_f["solidCount"] >= 1 and obs_f["zeroRoadMoments"] == 0 and obs_f["dashedAppearances"] == 0)
        results["test_f"] = {
            "pass": (backoff_ok and line_stayed_f),
            "attempts_recorded": len(reqs_f),
            "interval_1_sec": interval_1,
            "interval_2_sec": interval_2,
            "interval_3_sec": interval_3,
            "solid_paths_on_screen": st_f["solidCount"],
            "zero_road_moments": obs_f["zeroRoadMoments"],
            "dashed_appearances": obs_f["dashedAppearances"]
        }

        # =========================================================================
        # TEST (g): Pin elements keep DOM identity across 20 snapshot updates; remove/add stop
        # =========================================================================
        stops_g = make_initial_stops()
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_g)
        page.wait_for_timeout(400)

        initial_pin_count = page.evaluate("""() => {
            const pins = Array.from(document.querySelectorAll('.stop-pin-1'));
            window.__savedPinNodes = pins;
            return pins.length;
        }""")

        for i in range(20):
            page.evaluate(
                """([lat, lng, stops]) => {
                    window.__pushFirebase('trucks', {
                        '1': { truckId: 1, driverName: 'Ramesh Kumar', currentLat: lat, currentLng: lng, status: 'online', lastUpdated: Date.now() }
                    });
                    window.__pushFirebase('routes', { 'route_1': { stops } });
                }""",
                [base_lat + (i % 2) * 0.00001, base_lng, stops_g]
            )
            page.wait_for_timeout(30)

        page.wait_for_timeout(250)
        identity_preserved = page.evaluate("""() => {
            const curPins = Array.from(document.querySelectorAll('.stop-pin-1'));
            if (!window.__savedPinNodes || curPins.length !== window.__savedPinNodes.length || curPins.length === 0) return false;
            return curPins.every((el, idx) => el === window.__savedPinNodes[idx]);
        }""")

        # Remove stop 4 -> loses its pin
        stops_g_removed = make_initial_stops()
        del stops_g_removed["4"]
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_g_removed)
        page.wait_for_timeout(300)
        pin_count_after_remove = page.evaluate("document.querySelectorAll('.stop-pin-1').length")

        # Add stop 4 and stop 5 -> gains pins
        stops_g_added = make_initial_stops()
        stops_g_added["5"] = {
            "id": 5, "name": "Customer Epsilon", "address": "505 Lake Rd", "phone": "9876543214",
            "lat": 23.0360, "lng": 72.5890, "sequence": 5, "status": "PENDING", "confirmation": "CONFIRMED"
        }
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_g_added)
        page.wait_for_timeout(300)
        pin_count_after_add = page.evaluate("document.querySelectorAll('.stop-pin-1').length")

        results["test_g"] = {
            "pass": (initial_pin_count == 4 and identity_preserved and pin_count_after_remove == 3 and pin_count_after_add == 5),
            "initial_pins": initial_pin_count,
            "dom_identity_across_20_updates": identity_preserved,
            "pins_after_remove": pin_count_after_remove,
            "pins_after_add": pin_count_after_add
        }

        # =========================================================================
        # TEST (h) + Walkthrough: Two trucks visible, max 2 concurrent OSRM requests, Hide/Show toggles, click truck card, fitRouteBounds spy
        # =========================================================================
        page.evaluate("window.__osrmMockConfig.maxConcurrent = 0; window.__osrmMockConfig.delayMs = 120;")
        stops_t1 = {}
        stops_t2 = {}
        for i in range(1, 55):
            stops_t1[str(i)] = {
                "id": i, "name": f"T1 Stop {i}", "address": "Addr", "phone": "",
                "lat": 23.0400 + i * 0.0005, "lng": 72.5800 + i * 0.0005,
                "sequence": i, "status": "PENDING", "confirmation": "CONFIRMED"
            }
            stops_t2[str(1000 + i)] = {
                "id": 1000 + i, "name": f"T2 Stop {i}", "address": "Addr", "phone": "",
                "lat": 23.0100 - i * 0.0005, "lng": 72.5600 - i * 0.0005,
                "sequence": i, "status": "PENDING", "confirmation": "CONFIRMED"
            }

        page.evaluate(
            """([s1, s2, lat, lng]) => {
                visibleRouteTrucks.clear();
                renderRoutesOnMap();
                window.__pushFirebase('trucks', {
                    '1': { truckId: 1, driverName: 'Ramesh Kumar', currentLat: lat, currentLng: lng, status: 'online', lastUpdated: Date.now() },
                    '2': { truckId: 2, driverName: 'Suresh Patel', currentLat: lat - 0.02, currentLng: lng - 0.02, status: 'online', lastUpdated: Date.now() }
                });
                window.__pushFirebase('routes', {
                    'route_1': { stops: s1 },
                    'route_2': { stops: s2 }
                });
            }""",
            [stops_t1, stops_t2, base_lat, base_lng]
        )
        page.wait_for_timeout(300)

        # Spy on fitRouteBounds
        page.evaluate("""() => {
            window.__fitRouteBoundsCalls = 0;
            const origFit = window.fitRouteBounds;
            window.fitRouteBounds = function(id) {
                window.__fitRouteBoundsCalls++;
                return origFit.apply(this, arguments);
            };
        }""")

        # 1. Click "Show All Routes"
        page.click("#btn-toggle-all-routes")
        page.wait_for_timeout(900)

        max_conc = page.evaluate("window.__osrmMockConfig.maxConcurrent")
        both_visible = page.evaluate("Boolean(activeRouteLayers['1'] && activeRouteLayers['2'] && activeRouteLayers['1'].lines.length > 0 && activeRouteLayers['2'].lines.length > 0)")

        # 2. Click "Hide All Routes"
        page.click("#btn-toggle-all-routes")
        page.wait_for_timeout(200)
        after_hide_all = page.evaluate("Boolean(!activeRouteLayers['1'] && !activeRouteLayers['2'])")

        # 3. Click "Show All Routes" again to restore both
        page.click("#btn-toggle-all-routes")
        page.wait_for_timeout(400)
        restored_both = page.evaluate("""() => ({
            t1Present: Boolean(activeRouteLayers['1'] && activeRouteLayers['1'].lines.length > 0),
            t2Present: Boolean(activeRouteLayers['2'] && activeRouteLayers['2'].lines.length > 0)
        })""")

        # 4. Use "Hide Path" button on Truck 1 card only
        page.locator(".t-card").first.locator(".btn-route-toggle").click()
        page.wait_for_timeout(200)
        after_hide_t1 = page.evaluate("""() => ({
            t1Present: Boolean(activeRouteLayers['1']),
            t1Pins: document.querySelectorAll('.stop-pin-1').length,
            t2Present: Boolean(activeRouteLayers['2'] && activeRouteLayers['2'].lines.length > 0),
            t2Pins: document.querySelectorAll('.stop-pin-2').length
        })""")

        # 5. Click Truck 1 card -> expands card and pans/enables Truck 1 route
        page.locator(".t-card").first.click()
        page.wait_for_timeout(250)
        card_click_state = page.evaluate("""() => ({
            expanded: document.querySelector('.t-card').classList.contains('expanded'),
            t1RouteVisible: visibleRouteTrucks.has('1')
        })""")

        # 6. Verify fitRouteBounds does NOT fire on normal Firebase updates, ONLY on toggle
        fit_calls_before_updates = page.evaluate("window.__fitRouteBoundsCalls")
        page.evaluate(
            """([lat, lng]) => {
                window.__pushFirebase('trucks', {
                    '1': { truckId: 1, driverName: 'Ramesh Kumar', currentLat: lat + 0.0001, currentLng: lng, status: 'online', lastUpdated: Date.now() },
                    '2': { truckId: 2, driverName: 'Suresh Patel', currentLat: lat - 0.02, currentLng: lng - 0.02, status: 'online', lastUpdated: Date.now() }
                });
            }""",
            [base_lat, base_lng]
        )
        page.wait_for_timeout(300)
        fit_calls_after_updates = page.evaluate("window.__fitRouteBoundsCalls")
        page.evaluate("toggleTruckRoute('1', true)")
        fit_calls_after_toggle = page.evaluate("window.__fitRouteBoundsCalls")

        results["test_h"] = {
            "pass": (
                max_conc <= 2
                and both_visible
                and after_hide_all
                and not after_hide_t1["t1Present"]
                and after_hide_t1["t1Pins"] == 0
                and after_hide_t1["t2Present"]
                and after_hide_t1["t2Pins"] > 0
                and restored_both["t1Present"]
                and restored_both["t1Present"]
                and card_click_state["expanded"]
                and card_click_state["t1RouteVisible"]
                and fit_calls_after_updates == fit_calls_before_updates
                and fit_calls_after_toggle > fit_calls_after_updates
            ),
            "max_concurrent_osrm": max_conc,
            "after_hide_all": after_hide_all,
            "after_hide_t1": after_hide_t1,
            "restored_both": restored_both,
            "card_click_state": card_click_state,
            "fit_bounds_on_update_delta": fit_calls_after_updates - fit_calls_before_updates,
            "fit_bounds_on_toggle_delta": fit_calls_after_toggle - fit_calls_after_updates
        }

        # =========================================================================
        # TEST (i): Page reload with populated sessionStorage cache: no dashed line is ever shown
        # =========================================================================
        stops_i = make_initial_stops()
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", stops_i)
        page.evaluate("toggleTruckRoute('1', true)")
        page.wait_for_timeout(400)

        cache_keys_count = page.evaluate("Object.keys(sessionStorage).filter(k => k.startsWith('osrm_')).length")

        # Reload page with sessionStorage intact
        page.reload(wait_until="domcontentloaded")
        page.evaluate(OBSERVER_INIT_JS)
        page.evaluate("window.__initOverlayObserver()")
        # Force observer to monitor EVERY dashed line from the very beginning of reload!
        page.evaluate("window.__obs.firstRoadDrawn = true; window.__resetObserverCounters();")

        page.evaluate(
            """([lat, lng, stops]) => {
                window.__pushFirebase('trucks', {
                    '1': { truckId: 1, driverName: 'Ramesh Kumar', currentLat: lat, currentLng: lng, status: 'online', lastUpdated: Date.now() }
                });
                window.__pushFirebase('routes', {
                    'route_1': { stops: stops }
                });
                toggleTruckRoute('1', true);
            }""",
            [base_lat, base_lng, stops_i]
        )
        page.wait_for_timeout(400)
        obs_i = page.evaluate("window.__obs")
        st_i = page.evaluate("window.__inspectOverlay()")

        results["test_i"] = {
            "pass": (cache_keys_count > 0 and obs_i["dashedAppearances"] == 0 and st_i["dashedCount"] == 0 and st_i["solidCount"] >= 1),
            "session_storage_keys": cache_keys_count,
            "dashed_appearances_on_reload": obs_i["dashedAppearances"],
            "solid_paths_after_reload": st_i["solidCount"]
        }

        # =========================================================================
        # TEST: Multi-customer at same location: count badge, popup, and spiderfy
        # =========================================================================
        multi_stops = {
            "1": {
                "id": 1, "name": "Customer 1A", "address": "Flat 101, Galaxy Heights", "phone": "9999911111",
                "lat": 23.0250, "lng": 72.5800, "sequence": 1, "status": "PENDING", "confirmation": "CONFIRMED"
            },
            "2": {
                "id": 2, "name": "Customer 1B", "address": "Flat 102, Galaxy Heights", "phone": "9999922222",
                "lat": 23.0250, "lng": 72.5800, "sequence": 2, "status": "PENDING", "confirmation": "CONFIRMED"
            },
            "3": {
                "id": 3, "name": "Customer Gamma", "address": "Separate Location", "phone": "",
                "lat": 23.0300, "lng": 72.5850, "sequence": 3, "status": "PENDING", "confirmation": "CONFIRMED"
            }
        }
        page.evaluate("stops => window.__pushFirebase('routes', { 'route_1': { stops } })", multi_stops)
        page.evaluate("toggleTruckRoute('1', true)")
        page.wait_for_timeout(400)

        badge_info = page.evaluate("""() => {
            const pinEls = Array.from(document.querySelectorAll('.stop-pin-1'));
            const badges = pinEls.map(el => {
                const b = el.querySelector('span');
                return b ? b.innerText.trim() : null;
            }).filter(Boolean);
            const m = activeRouteLayers['1'] ? activeRouteLayers['1'].stopMarkers['1'] : null;
            const popupHtml = m ? m.popupHtml : '';
            return {
                badges: badges,
                hasBothCustomersInPopup: popupHtml.includes('Customer 1A') && popupHtml.includes('Customer 1B') && popupHtml.includes('2 Customers')
            };
        }""")

        # Click the cluster marker to trigger spiderfy
        page.evaluate("""() => {
            const m = activeRouteLayers['1'] ? activeRouteLayers['1'].stopMarkers['1'] : null;
            if (m && m.marker) m.marker.fire('click');
        }""")
        page.wait_for_timeout(200)
        spider_count = page.evaluate("document.querySelectorAll('.spider-child-pin-1').length")

        # Unspiderfy on second click
        page.evaluate("""() => {
            const m = activeRouteLayers['1'] ? activeRouteLayers['1'].stopMarkers['1'] : null;
            if (m && m.marker) m.marker.fire('click');
        }""")
        page.wait_for_timeout(200)
        spider_count_after_collapse = page.evaluate("document.querySelectorAll('.spider-child-pin-1').length")

        results["multi_customer_location"] = {
            "pass": (
                "2" in badge_info["badges"]
                and badge_info["hasBothCustomersInPopup"]
                and spider_count == 2
                and spider_count_after_collapse == 0
            ),
            "badges_found": badge_info["badges"],
            "hasBothCustomersInPopup": badge_info["hasBothCustomersInPopup"],
            "spider_fanned_pins": spider_count,
            "spider_pins_after_collapse": spider_count_after_collapse
        }

        # =========================================================================
        # TEST (j): No console errors or page errors in any scenario
        # =========================================================================
        results["test_j"] = {
            "pass": (len(console_errors) == 0 and len(page_errors) == 0),
            "console_errors": console_errors,
            "page_errors": page_errors
        }

        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()

        if video_path and record_video_name and os.path.exists(video_path):
            target_video = os.path.join(video_dir, record_video_name)
            if os.path.exists(target_video):
                os.remove(target_video)
            os.rename(video_path, target_video)
            results["video_path"] = target_video

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Live Route Flicker on live_tracking.html")
    parser.add_argument("html_path", help="Path to the HTML file to test (before or fixed)")
    parser.add_argument("--skip-60s", action="store_true", help="Skip the 60s jitter test for quick iteration")
    parser.add_argument("--video-name", default=None, help="Filename for recorded video in scratch/videos")
    args = parser.parse_args()

    res = run_test_suite(args.html_path, run_60s_jitter=not args.skip_60s, record_video_name=args.video_name)
    print(json.dumps(res, indent=2))

    # Exit with code 0 only if all executed tests passed
    all_passed = all(
        v.get("pass", True)
        for k, v in res.items()
        if isinstance(v, dict) and "pass" in v
    )
    sys.exit(0 if all_passed else 1)
