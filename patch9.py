import io
with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_render_start = '''        function render() {
            console.log("[RENDER] Running render | Current Index:", currentIndex);
            
            currentRenderId++;
            let thisRenderId = currentRenderId;'''

new_render_start = '''        function render() {
            console.log("[RENDER] Running render | Current Index:", currentIndex);
            
            let savedScrollTop = 0;
            let groupListEl = document.getElementById('group-customer-list');
            if (groupListEl) savedScrollTop = groupListEl.scrollTop;
            
            let savedSkipModalVal = null;
            let skipModal = document.getElementById('groupSkipModalOverlay');
            if (skipModal) {
                let checkedRadio = document.querySelector('input[name="skipCustomerRadio"]:checked');
                if (checkedRadio) savedSkipModalVal = checkedRadio.value;
            }
            
            currentRenderId++;
            let thisRenderId = currentRenderId;'''

text = text.replace(old_render_start, new_render_start)

old_render_end = '''            document.getElementById('truck-title').innerText = "Offline";
        };'''

new_render_end = '''            document.getElementById('truck-title').innerText = "Offline";
            
            // Restore scroll and modal
            let newGroupListEl = document.getElementById('group-customer-list');
            if (newGroupListEl && savedScrollTop > 0) newGroupListEl.scrollTop = savedScrollTop;
            
            if (skipModal && currentIndex < stops.length) {
                let stop = stops[currentIndex];
                if (stop.subStops && stop.subStops.length > 1) {
                    openGroupSkipModal(stop);
                    if (savedSkipModalVal) {
                        let radio = document.querySelector(`input[name="skipCustomerRadio"][value="${savedSkipModalVal}"]`);
                        if (radio) {
                            radio.checked = true;
                            document.getElementById('skipSelectedBtn').disabled = false;
                        }
                    }
                } else {
                    closeGroupSkipModal();
                }
            } else if (skipModal) {
                closeGroupSkipModal();
            }
        };'''

text = text.replace(old_render_end, new_render_end)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
