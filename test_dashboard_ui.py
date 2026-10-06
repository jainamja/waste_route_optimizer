import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/opt/pw-browsers/chromium', headless=True)
        page = await browser.new_page()

        # Mock CDNs
        await page.route("**/*.js", lambda route: route.fulfill(body="", status=200))
        await page.route("**/*.css", lambda route: route.fulfill(body="", status=200))
        
        # Mock APIs
        mock_data = {
            "customers": [
                {"id": 1, "name": "C1", "truck": "1", "stop_number": 1, "confirmation": "NOT_CONFIRMED"},
                {"id": 2, "name": "C2", "truck": "1", "stop_number": 2, "confirmation": "NOT_CONFIRMED"},
                {"id": 3, "name": "C3", "truck": "1", "stop_number": 3, "confirmation": "CONFIRMED"},
                {"id": -1001, "name": "End Location / Depot", "truck": "1"}
            ],
            "drivers": [
                {"id": 10, "name": "D1", "truck_id": None}
            ],
            "routes": [[1, 2, 3, -1001]],
            "start_coords": ["0,0"],
            "end_coords": ["1,1"]
        }
        
        await page.route("**/api/data", lambda route: route.fulfill(json=mock_data))
        
        assign_requests = []
        async def handle_assign(route):
            assign_requests.append(route.request.post_data_json)
            await route.fulfill(json={"success": True, "firebase_synced": True})
            
        await page.route("**/api/assign_driver", handle_assign)
        
        # We need to serve the HTML. But we can just set content directly.
        with open("templates/live_dashboard.html", "r", encoding="utf-8") as f:
            html = f.read()
            
        await page.set_content(html)
        
        # We need to trigger loadData since body onload might not fire if we mock scripts.
        await page.evaluate("loadData()")
        await page.wait_for_timeout(500)
        
        # 1. Open Assign Driver
        await page.evaluate("openAssignModal('1')")
        
        # 2. Pick a driver
        await page.locator("#assign-driver-select").select_option("10")
        
        # 3. Click Next
        await page.locator("#btn-assign-next").click()
        await page.wait_for_timeout(100)
        
        # 4. Tick 2 customers (C1 and C2)
        # Checkboxes are bound to `toggleConf('1')` and `toggleConf('2')`
        await page.evaluate("toggleConf('1')")
        await page.evaluate("toggleConf('2')")
        
        # 5. Click Back
        await page.locator("#btn-conf-back").click()
        await page.wait_for_timeout(100)
        
        # 6. Click Next again
        await page.locator("#btn-assign-next").click()
        await page.wait_for_timeout(100)
        
        # 7. Click Assign & Save
        await page.locator("#btn-conf-save").click()
        await page.wait_for_timeout(500)
        
        assert len(assign_requests) == 1, "API should be called once"
        req = assign_requests[0]
        
        assert req["driver_id"] == 10, "driver_id should be integer"
        assert req["truck_id"] == 1, "truck_id should be integer"
        
        # Expected confirmations: C1 changed to CONFIRMED, C2 changed to CONFIRMED, C3 remains CONFIRMED
        conf = req["confirmations"]
        assert conf["1"] == "CONFIRMED"
        assert conf["2"] == "CONFIRMED"
        assert conf["3"] == "CONFIRMED"
        assert "-1001" not in conf, "Depot should be excluded"
        
        print("Dashboard UI Test Passed")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
