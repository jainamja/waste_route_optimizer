import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/opt/pw-browsers/chromium', headless=True)
        page = await browser.new_page()

        await page.route("**/*.js", lambda route: route.fulfill(body="", status=200))
        await page.route("**/*.css", lambda route: route.fulfill(body="", status=200))
        
        with open("templates/driver_view.html", "r", encoding="utf-8") as f:
            html = f.read()
            
        await page.set_content(html)
        
        # Inject mocked variables so render() works
        await page.evaluate("""
            window.stops = [
                {
                    id: 1, name: "S1", address: "A1", lat: 0, lng: 0, status: 'PENDING',
                    confirmation: "CONFIRMED"
                },
                {
                    id: 2, name: "S2", address: "A2", lat: 0, lng: 0, status: 'PENDING',
                    confirmation: "NOT_CONFIRMED"
                },
                {
                    // Grouped Stop
                    name: "Group", address: "A3", lat: 0, lng: 0, status: 'PENDING',
                    subStops: [
                        {id: 3, name: "S3", confirmation: "CONFIRMED", status: 'PENDING'},
                        {id: 4, name: "S4", confirmation: "NOT_CONFIRMED", status: 'PENDING'}
                    ]
                }
            ];
            window.currentIndex = 0;
            window.map = {
                removeLayer: () => {}, flyTo: () => {}, fitBounds: () => {}
            };
            window.routeLine = null;
            window.routeMarkers = [];
            window.markerCluster = null;
            window.L = {
                markerClusterGroup: () => ({}),
                divIcon: () => ({})
            };
            window.calculateSnapPoints = () => {};
            
            render();
        """)
        
        # Now verify DOM
        # Current stop card is S1
        # It should have #ecfdf5 background and #10b981 border, text 'Confirmed'
        current_html = await page.locator("#current-stop-container").inner_html()
        assert "#ecfdf5" in current_html, "S1 should be green"
        assert "#10b981" in current_html, "S1 should have green border"
        assert "Confirmed" in current_html, "S1 should have Confirmed badge"
        
        # Stop list should have 3 items.
        # S1 -> Confirmed
        # S2 -> Not confirmed (#eff6ff, #2F5FFF)
        # Group -> 1 confirmed · 1 not (linear-gradient)
        list_items = await page.locator(".stop-item").all()
        assert len(list_items) == 3
        
        html1 = await list_items[0].inner_html()
        assert "Confirmed" in html1
        
        html2 = await list_items[1].inner_html()
        assert "Not confirmed" in html2
        
        html3 = await list_items[2].inner_html()
        assert "1 confirmed · 1 not" in html3
        
        print("Driver UI Test Passed")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
