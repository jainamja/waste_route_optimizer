import io

with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

# For subStops grouping
old_sub_map = """                            let bg = cConf ? '#ecfdf5' : '#eff6ff';
                            let brd = cConf ? '#10b981' : '#2F5FFF';
                            let txt = cConf ? 'Confirmed' : 'Not confirmed';"""
new_sub_map = """                            let isInactive = ss.customer_status === 'INACTIVE';
                            let bg = isInactive ? '#fef2f2' : (cConf ? '#ecfdf5' : '#eff6ff');
                            let brd = isInactive ? '#ef4444' : (cConf ? '#10b981' : '#2F5FFF');
                            let txt = isInactive ? 'INACTIVE' : (cConf ? 'Confirmed' : 'Not confirmed');"""
text = text.replace(old_sub_map, new_sub_map)

# For subStops single
old_single_map = """                    let bg = cConf ? '#ecfdf5' : '#eff6ff';
                    let brd = cConf ? '#10b981' : '#2F5FFF';
                    let txt = cConf ? 'Confirmed' : 'Not confirmed';"""
new_single_map = """                    let isInactive = single.customer_status === 'INACTIVE';
                    let bg = isInactive ? '#fef2f2' : (cConf ? '#ecfdf5' : '#eff6ff');
                    let brd = isInactive ? '#ef4444' : (cConf ? '#10b981' : '#2F5FFF');
                    let txt = isInactive ? 'INACTIVE' : (cConf ? 'Confirmed' : 'Not confirmed');"""
text = text.replace(old_single_map, new_single_map)

# For badgeHtml fallback
old_badge = """                        let cConf = s.confirmation === 'CONFIRMED';
                        let bg = cConf ? '#ecfdf5' : '#eff6ff';
                        let brd = cConf ? '#10b981' : '#2F5FFF';
                        let txt = cConf ? 'Confirmed' : 'Not confirmed';
                        confStyle = `background:${bg}; border-left: var(--conf-strip) solid ${brd};`;
                        badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:${brd};">${txt}</div>`;"""
new_badge = """                        let cConf = s.confirmation === 'CONFIRMED';
                        let isInactive = s.customer_status === 'INACTIVE';
                        let bg = isInactive ? '#fef2f2' : (cConf ? '#ecfdf5' : '#eff6ff');
                        let brd = isInactive ? '#ef4444' : (cConf ? '#10b981' : '#2F5FFF');
                        let txt = isInactive ? 'INACTIVE' : (cConf ? 'Confirmed' : 'Not confirmed');
                        confStyle = `background:${bg}; border-left: var(--conf-strip) solid ${brd};`;
                        badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:${brd};">${txt}</div>`;"""
text = text.replace(old_badge, new_badge)

# For skipRadioGroup
old_radio = """                                let cConf = ss.confirmation === 'CONFIRMED';
                                let bg = cConf ? '#ecfdf5' : '#eff6ff';
                                let brd = cConf ? '#10b981' : '#2F5FFF';
                                let txt = cConf ? 'Confirmed' : 'Not confirmed';"""
new_radio = """                                let cConf = ss.confirmation === 'CONFIRMED';
                                let isInactive = ss.customer_status === 'INACTIVE';
                                let bg = isInactive ? '#fef2f2' : (cConf ? '#ecfdf5' : '#eff6ff');
                                let brd = isInactive ? '#ef4444' : (cConf ? '#10b981' : '#2F5FFF');
                                let txt = isInactive ? 'INACTIVE' : (cConf ? 'Confirmed' : 'Not confirmed');"""
text = text.replace(old_radio, new_radio)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Replaced:", text.count("isInactive"))
