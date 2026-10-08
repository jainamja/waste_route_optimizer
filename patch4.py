import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_block = '''                if(result.success) {
                    if (result.firebase_synced === false) {
                        alert("Saved, but the driver app could not be updated (Firebase sync failed). Please try again.");
                    }
                    currentConfData = null; // Clear so next open is fresh
                    closeConfModal();
                    loadData();
                } else {'''

new_block = '''                if(result.success) {
                    if (result.refused_cancel && result.refused_cancel.length > 0) {
                        let names = result.refused_cancel.map(id => {
                            let c = currentConfData[id] || data.customers.find(x => x.id == id);
                            return c ? c.name : id;
                        }).join(', ');
                        alert("Saved, but the following customers could not be cancelled because they are already collected: " + names);
                    } else if (result.firebase_synced === false) {
                        alert("Saved, but the driver app could not be updated (Firebase sync failed). Please try again.");
                    }
                    currentConfData = null; // Clear so next open is fresh
                    closeConfModal();
                    loadData();
                } else {'''

text = text.replace(old_block, new_block)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
