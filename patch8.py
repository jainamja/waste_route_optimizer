import io
with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_style = '''                let badgeHtml = '';
                if (!isDepot) {
                    if (s.subStops && s.subStops.length > 1) {
                        let cCount = s.subStops.filter(x => x.confirmation === 'CONFIRMED').length;
                        let nCount = s.subStops.length - cCount;
                        if (nCount === 0) {
                            confStyle = 'background:#ecfdf5; border-left: var(--conf-strip) solid #10b981;';
                            badgeHtml = '<div style="font-size:10px; font-weight:700; margin-top:4px; color:#10b981;">Confirmed</div>';
                        } else if (cCount === 0) {
                            confStyle = 'background:#eff6ff; border-left: var(--conf-strip) solid #2F5FFF;';
                            badgeHtml = '<div style="font-size:10px; font-weight:700; margin-top:4px; color:#2F5FFF;">Not confirmed</div>';
                        } else {
                            confStyle = 'background: linear-gradient(90deg, #ecfdf5 50%, #eff6ff 50%); border-left: var(--conf-strip) solid #10b981; border-right: var(--conf-strip) solid #2F5FFF;';
                            badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:var(--text-main);">${cCount} confirmed \u00B7 ${nCount} not</div>`;
                        }
                    } else {
                        let cConf = s.confirmation === 'CONFIRMED';
                        let bg = cConf ? '#ecfdf5' : '#eff6ff';
                        let brd = cConf ? '#10b981' : '#2F5FFF';
                        let txt = cConf ? 'Confirmed' : 'Not confirmed';
                        confStyle = `background:${bg}; border-left: var(--conf-strip) solid ${brd};`;
                        badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:${brd};">${txt}</div>`;
                    }
                }'''

new_style = '''                let badgeHtml = '';
                if (!isDepot) {
                    if (s.subStops && s.subStops.length > 1) {
                        let cCount = s.subStops.filter(x => x.confirmation === 'CONFIRMED').length;
                        let cancCount = s.subStops.filter(x => x.confirmation === 'CANCELLED').length;
                        let nCount = s.subStops.length - cCount - cancCount;
                        let actionableTotal = s.subStops.length - cancCount;
                        
                        if (actionableTotal === 0) {
                            // fully cancelled group
                            confStyle = 'background:#fef2f2; border-left: var(--conf-strip) solid #ef4444; opacity: 0.6;';
                            badgeHtml = '<div style="font-size:10px; font-weight:700; margin-top:4px; color:#ef4444; text-decoration:line-through;">Cancelled</div>';
                        } else if (nCount === 0) {
                            confStyle = 'background:#ecfdf5; border-left: var(--conf-strip) solid #10b981;';
                            badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:#10b981;">Confirmed ${cancCount > 0 ? `(+${cancCount} cancelled)` : ''}</div>`;
                        } else if (cCount === 0) {
                            confStyle = 'background:#eff6ff; border-left: var(--conf-strip) solid #2F5FFF;';
                            badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:#2F5FFF;">Not confirmed ${cancCount > 0 ? `(+${cancCount} cancelled)` : ''}</div>`;
                        } else {
                            confStyle = 'background: linear-gradient(90deg, #ecfdf5 50%, #eff6ff 50%); border-left: var(--conf-strip) solid #10b981; border-right: var(--conf-strip) solid #2F5FFF;';
                            badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:var(--text-main);">${cCount} confirmed \u00B7 ${nCount} not ${cancCount > 0 ? `(+${cancCount} cancelled)` : ''}</div>`;
                        }
                    } else {
                        let isCanc = s.confirmation === 'CANCELLED';
                        let isConf = s.confirmation === 'CONFIRMED';
                        let bg = isCanc ? '#fef2f2' : (isConf ? '#ecfdf5' : '#eff6ff');
                        let brd = isCanc ? '#ef4444' : (isConf ? '#10b981' : '#2F5FFF');
                        let txt = isCanc ? 'Cancelled' : (isConf ? 'Confirmed' : 'Not confirmed');
                        
                        confStyle = `background:${bg}; border-left: var(--conf-strip) solid ${brd};`;
                        if (isCanc) confStyle += ' opacity: 0.6;';
                        
                        let dec = isCanc ? 'text-decoration:line-through;' : '';
                        badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:${brd}; ${dec}">${txt}</div>`;
                    }
                }'''

text = text.replace(old_style, new_style)

old_list_item_html = '''                return `
                <div class="${classes}" onclick="handleStopClick(${idx})" style="${confStyle}">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div style="flex:1;">
                            <div class="stop-list-name">${s.name} ${s.id && s.id > 0 ? `(Sr. ${s.id})` : ''}</div>
                            ${isDepot ? '' : `<div class="stop-list-addr">${s.address || 'No exact address'}</div>`}
                            ${badgeHtml}
                        </div>
                        ${statusLabel}
                    </div>
                </div>
                `;'''

new_list_item_html = '''                let isCanc = !isDepot && (s.confirmation === 'CANCELLED' || (s.subStops && s.subStops.length === s.subStops.filter(ss=>ss.confirmation==='CANCELLED').length));
                let nameDec = isCanc ? 'text-decoration:line-through;' : '';
                return `
                <div class="${classes}" onclick="handleStopClick(${idx})" style="${confStyle}">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div style="flex:1;">
                            <div class="stop-list-name" style="${nameDec}">${s.name} ${s.id && s.id > 0 ? `(Sr. ${s.id})` : ''}</div>
                            ${isDepot ? '' : `<div class="stop-list-addr">${s.address || 'No exact address'}</div>`}
                            ${badgeHtml}
                        </div>
                        ${statusLabel}
                    </div>
                </div>
                `;'''
text = text.replace(old_list_item_html, new_list_item_html)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
