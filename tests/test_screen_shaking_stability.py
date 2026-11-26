import os
import re
import pytest

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '..', 'templates', 'live_tracking.html')

@pytest.fixture
def template_content():
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        return f.read()

def test_map_initializes_exactly_once(template_content):
    """Requirement 1: Map initializes exactly once per page lifecycle."""
    map_inits = re.findall(r'L\.map\(', template_content)
    assert len(map_inits) == 1, f"Expected exactly 1 L.map() initialization, found {len(map_inits)}"

def test_viewport_stability_during_gps_updates(template_content):
    """Requirement 2: Routine GPS events do not reset map center or zoom."""
    # Ensure fitBounds is strictly guarded by hasFitBounds flag
    assert 'if (hasLive && !window.hasFitBounds)' in template_content, "fitBounds not guarded by window.hasFitBounds"
    # Ensure setView only called once at map init
    set_view_calls = re.findall(r'\.setView\(', template_content)
    assert len(set_view_calls) == 1, f"Expected exactly 1 .setView() call, found {len(set_view_calls)}"

def test_markers_updated_instead_of_recreated(template_content):
    """Requirement 3: Existing markers are updated instead of recreated."""
    assert 'if (liveTruckMarkers[tId])' in template_content
    assert 'animateTruckMarker(liveTruckMarkers[tId]' in template_content
    # Deadband filter to prevent micro-jitter
    assert 'dist < 1.0 && Math.abs(diffHeading) < 5' in template_content
    # CSS transition disabled on .leaflet-marker-icon to prevent transform fighting
    assert '.leaflet-marker-icon {' in template_content
    assert 'transition: none !important;' in template_content

def test_firebase_listener_deduplication(template_content):
    """Requirement 4: Firebase reconnect does not create duplicate listeners."""
    assert 'registerFirebaseListener' in template_content
    assert 'window.activeFirebaseListeners' in template_content
    assert 'if (window.activeFirebaseListeners[key]) return;' in template_content

def test_unchanged_route_geometry_not_redrawn(template_content):
    """Requirement 5: Unchanged route geometry is not repeatedly redrawn."""
    assert 'window._routesNeedRender' in template_content
    assert 'if (!force && !window._routesNeedRender) return;' in template_content

def test_dashboard_updates_preserve_map_container(template_content):
    """Requirement 6: Dashboard updates do not replace or destroy the map container."""
    # Ensure #map is outside progress-panel and truck-list
    assert '<div id="map"></div>' in template_content
    # Ensure progress stats update in place (Zero CLS)
    assert 'stat-comp' in template_content
    assert 'stat-skip' in template_content
    assert 'stat-canc' in template_content
    assert 'stat-left' in template_content
    assert 'stat-pct' in template_content

def test_layout_stability_css(template_content):
    """Requirement 7: No unexpected layout shifts occur during normal telemetry updates."""
    # Ensure html and body have overflow: hidden
    assert 'html { height: 100vh; overflow: hidden;' in template_content
    assert 'body { font-family: \'Inter\', sans-serif; background: var(--bg); color: var(--text-main); height: 100vh; overflow: hidden;' in template_content
    # Ensure header-bar is flex-shrink: 0
    assert '.header-bar {' in template_content
    assert 'flex-shrink: 0;' in template_content
    # Ensure pulse-dot has fixed dimensions
    assert '.pulse-dot {' in template_content
    assert 'width: 8px; height: 8px;' in template_content

def test_page_lifecycle_cleanup(template_content):
    """Requirement 8: Page cleanup removes obsolete listeners and timers."""
    assert 'window.cleanupLiveTracking' in template_content
    assert 'window.addEventListener(\'beforeunload\', window.cleanupLiveTracking)' in template_content
    assert 'cancelAnimationFrame' in template_content
    assert 'unregisterFirebaseListener' in template_content
