import io

with io.open('templates/live_tracking.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Remove updateMapPopups() from listeners
text = text.replace("updateMapPopups();\n                scheduleRender();", "scheduleRender();")
text = text.replace("updateMapPopups();\n                        scheduleRender();", "scheduleRender();")

# Add it at the end of renderProgress()
old_end = """            document.getElementById('fleet-prog-bar').innerHTML = `
                <div class="prog-bar-comp" style="width: ${fleetTotal > 0 ? (fleetComp/fleetTotal)*100 : 0}%"></div>
                <div class="prog-bar-skip" style="width: ${fleetTotal > 0 ? (fleetSkip/fleetTotal)*100 : 0}%"></div>
            `;
        }"""

new_end = """            document.getElementById('fleet-prog-bar').innerHTML = `
                <div class="prog-bar-comp" style="width: ${fleetTotal > 0 ? (fleetComp/fleetTotal)*100 : 0}%"></div>
                <div class="prog-bar-skip" style="width: ${fleetTotal > 0 ? (fleetSkip/fleetTotal)*100 : 0}%"></div>
            `;
            
            // Sync map popups and markers AFTER state is fully processed
            updateMapPopups();
        }"""

text = text.replace(old_end, new_end)

with io.open('templates/live_tracking.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
