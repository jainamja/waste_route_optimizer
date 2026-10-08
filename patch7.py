import io
with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_markStop = '''        window.markStop = function(status) {
            console.log("[MARK STOP] Tapped:", status, "| Current Index:", currentIndex);
            if (currentIndex < stops.length) {
                const stop = stops[currentIndex];
                
                if (status === 'SKIPPED' && stop.subStops && stop.subStops.length > 1) {
                    // Open Group Skip Modal
                    openGroupSkipModal(stop);
                    return;
                }
                
                let updates = {};
                if (stop.subStops) {
                    stop.subStops.forEach(ss => {
                        // Only mark as COMPLETED/SKIPPED if still PENDING
                        if (ss.status === 'PENDING') {
                            updates[ss.id + "/status"] = status;
                        }
                    });
                } else {
                    updates[stop.id + "/status"] = status;
                }'''

new_markStop = '''        window.markStop = function(status) {
            console.log("[MARK STOP] Tapped:", status, "| Current Index:", currentIndex);
            if (currentIndex < stops.length) {
                const stop = stops[currentIndex];
                
                let actionableSubStops = stop.subStops ? stop.subStops.filter(ss => ss.status === 'PENDING' && ss.confirmation !== 'CANCELLED') : [];
                
                if (status === 'SKIPPED' && stop.subStops && stop.subStops.length > 1) {
                    // Open Group Skip Modal
                    openGroupSkipModal(stop);
                    return;
                }
                
                let updates = {};
                if (stop.subStops) {
                    stop.subStops.forEach(ss => {
                        // Only mark actionable as COMPLETED/SKIPPED
                        if (ss.status === 'PENDING' && ss.confirmation !== 'CANCELLED') {
                            updates[ss.id + "/status"] = status;
                        }
                    });
                } else {
                    if (stop.confirmation !== 'CANCELLED') {
                        updates[stop.id + "/status"] = status;
                    }
                }'''

text = text.replace(old_markStop, new_markStop)

old_modal = '''        window.openGroupSkipModal = function(stop) {
            let pendingSubStops = stop.subStops.filter(ss => ss.status === 'PENDING');
            if (pendingSubStops.length === 0) return;'''
new_modal = '''        window.openGroupSkipModal = function(stop) {
            let pendingSubStops = stop.subStops.filter(ss => ss.status === 'PENDING' && ss.confirmation !== 'CANCELLED');
            if (pendingSubStops.length === 0) return;'''
text = text.replace(old_modal, new_modal)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
