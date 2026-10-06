"""
Playwright tests for driver_view.html:
- Grouped stops scrollable card (#group-customer-list)
- 8px confirmation strips (var(--conf-strip) = 8px)
- Sticky action buttons
- calculateSnapPoints grouped-mode snap math
"""
import re
import pytest
from playwright.sync_api import Page, expect


HTML_FILE = "templates/driver_view.html"


# ---------------------------------------------------------------------------
# Helper: read the raw HTML so we can do static checks without a server
# ---------------------------------------------------------------------------

def read_html() -> str:
    with open(HTML_FILE, encoding="utf-8") as f:
        return f.read()


# ===========================================================================
# Static (source-level) tests — fast, no browser needed
# ===========================================================================

class TestStaticSource:
    def test_conf_strip_variable_declared(self):
        """--conf-strip: 8px must be in the :root block."""
        html = read_html()
        assert "--conf-strip: 8px;" in html, "--conf-strip CSS variable not found"

    def test_no_hardcoded_4px_border_left(self):
        """No border-left:4px should remain — all must use var(--conf-strip)."""
        html = read_html()
        assert "border-left:4px" not in html, "Found hardcoded border-left:4px"

    def test_legend_swatches_6px(self):
        """Legend swatches must use 6px border and 18px width."""
        html = read_html()
        assert "border-left:6px solid #10b981" in html
        assert "border-left:6px solid #2F5FFF" in html
        assert 'width:18px' in html

    def test_group_customer_list_element(self):
        """group-customer-list div with overflow-y:auto must be present in JS template."""
        html = read_html()
        assert 'id="group-customer-list"' in html
        assert "overflow-y:auto" in html

    def test_group_card_header_element(self):
        """group-card-header div must be in JS template."""
        html = read_html()
        assert 'id="group-card-header"' in html

    def test_action_buttons_sticky(self):
        """action-buttons must have position:sticky style."""
        html = read_html()
        assert 'position:sticky' in html
        assert 'bottom:0' in html

    def test_current_stop_container_overflow(self):
        """#current-stop-container CSS must have overflow-y: auto."""
        html = read_html()
        assert "#current-stop-container" in html
        # Find the CSS rule block
        match = re.search(r'#current-stop-container\s*\{([^}]+)\}', html)
        assert match, "#current-stop-container CSS rule not found"
        rule_body = match.group(1)
        assert "overflow-y" in rule_body
        assert "auto" in rule_body

    def test_calculate_snap_points_uses_group_elements(self):
        """calculateSnapPoints must reference group-card-header and group-customer-list."""
        html = read_html()
        assert "group-card-header" in html
        assert "group-customer-list" in html
        # Also check the 85% cap
        assert "0.85" in html

    def test_update_fab_clamp(self):
        """updateFabPosition must clamp using navbar bounding rect."""
        html = read_html()
        assert "getBoundingClientRect" in html
        assert "maxBottom" in html
        assert "Math.min(desiredBottom, maxBottom)" in html

    def test_drag_listener_smart_scroll(self):
        """Smart drag listener must check group-customer-list scroll position."""
        html = read_html()
        assert "group-customer-list" in html
        assert "scrollTop" in html
        assert "handleFirstMove" in html

    def test_orientation_change_listener(self):
        """orientationchange listener must be present."""
        html = read_html()
        assert "orientationchange" in html

    def test_pending_count_in_header(self):
        """Group header must show pending count."""
        html = read_html()
        assert "pendingCount" in html
        assert "left" in html  # "X left" label

    def test_conf_strip_used_in_all_border_left(self):
        """Every border-left in JS templates must use var(--conf-strip)."""
        html = read_html()
        # Find all border-left occurrences and make sure none are plain px values
        occurrences = re.findall(r'border-left:\s*([^;]+);', html)
        for occ in occurrences:
            # Allow 6px for legend swatches only
            if "6px" in occ:
                continue
            assert "var(--conf-strip)" in occ, f"Found border-left without var(--conf-strip): {occ!r}"

    def test_src_index_matches_template(self):
        """src/index.html must be byte-for-byte identical to templates/driver_view.html."""
        import os
        with open("templates/driver_view.html", "rb") as f:
            template_bytes = f.read()
        with open("src/index.html", "rb") as f:
            src_bytes = f.read()
        assert template_bytes == src_bytes, "src/index.html does not match templates/driver_view.html"


# ===========================================================================
# Browser-level tests (require Playwright + a local dev server or file://)
# ===========================================================================

@pytest.fixture(scope="session")
def html_path():
    import os
    abs_path = os.path.abspath(HTML_FILE)
    return f"file:///{abs_path.replace(chr(92), '/')}"


@pytest.mark.skip(reason="Requires Firebase + live backend; run manually with --live flag")
class TestBrowserLive:
    """
    These tests need a running Firebase and backend.
    They are skipped in CI but can be run with pytest -k TestBrowserLive --no-header -rN.
    """

    def test_conf_strip_computed_value(self, page: Page, html_path: str):
        """--conf-strip computed value must be 8px in the browser."""
        page.goto(html_path)
        value = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--conf-strip').trim()"
        )
        assert value == "8px", f"--conf-strip is {value!r}, expected '8px'"

    def test_group_customer_list_scrollable(self, page: Page, html_path: str):
        """#group-customer-list must be scrollable (overflow-y auto/scroll)."""
        page.goto(html_path)
        overflow = page.evaluate(
            "getComputedStyle(document.getElementById('group-customer-list')).overflowY"
        )
        assert overflow in ("auto", "scroll"), f"group-customer-list overflow-y is {overflow!r}"

    def test_action_buttons_sticky_computed(self, page: Page, html_path: str):
        """action-buttons position must be sticky."""
        page.goto(html_path)
        pos = page.evaluate(
            "getComputedStyle(document.querySelector('.action-buttons')).position"
        )
        assert pos == "sticky", f".action-buttons position is {pos!r}"
