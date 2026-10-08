import io
import re

with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_group = '''                let subStopsHtml = '';
                if (stop.subStops && stop.subStops.length > 1) {
                    let pendingCount = stop.subStops.filter(ss => ss.status === 'PENDING').length;
                    subStopsHtml = `<div id="group-card-header" style="padding-bottom:8px;">
                        <div style="font-size: 13px; font-weight: 700; color: var(--primary); text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px;">${stop.subStops.length} Customers \u00B7 ${pendingCount} left</div>
                    </div>
                    <div id="group-customer-list" style="overflow-y:auto; overscroll-behavior:contain; -webkit-overflow-scrolling:touch; max-height:min(calc(55dvh - 100px), calc(55vh - 100px)); display:flex; flex-direction:column; gap:6px; margin-bottom:8px;">
                        ${stop.subStops.map((ss, i) => {
                            let cConf = ss.confirmation === 'CONFIRMED';
                            let bg = cConf ? '#ecfdf5' : '#eff6ff';
                            let brd = cConf ? '#10b981' : '#2F5FFF';
                            let txt = cConf ? 'Confirmed' : 'Not confirmed';
                            let statusLabel = ss.status === 'COMPLETED' ? ' <span style="color:#10b981;font-size:10px;">\u2713 Done</span>' : (ss.status === 'SKIPPED' ? ' <span style="color:#ef4444;font-size:10px;">\u2717 Skipped</span>' : '');
                            return `
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; background:${bg}; border-left: var(--conf-strip) solid ${brd}; padding:8px 10px; border-radius:8px;">
                                <div style="flex:1; min-width:0;">
                                    <div style="font-weight: 700; font-size: 14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:var(--text-main);">${ss.name} ${ss.id && ss.id > 0 ? `(Sr. ${ss.id})` : ''}</div>
                                    <div style="font-size: 12px; color: var(--text-muted); display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; margin-top:2px;">${ss.address || 'No exact address'}</div>
                                    <div style="font-size:10px; font-weight:700; margin-top:4px; color:${brd};">${txt}</div>
                                </div>
                                ${ss.phone ? `<a href="tel:${ss.phone}" style="background: var(--primary); color: white; width: 32px; height: 32px; min-width:32px; border-radius: 50%; display: flex; justify-content: center; align-items: center; text-decoration: none; margin-left:8px;"><i class="fa-solid fa-phone" style="font-size:13px;"></i></a>` : ''}
                            </div>
                        `;
                        }).join('')}
                    </div>`;
                } else {
                    let single = stop.subStops ? stop.subStops[0] : stop;
                    let cConf = single.confirmation === 'CONFIRMED';
                    let bg = cConf ? '#ecfdf5' : '#eff6ff';
                    let brd = cConf ? '#10b981' : '#2F5FFF';
                    let txt = cConf ? 'Confirmed' : 'Not confirmed';
                    
                    subStopsHtml = `
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; background:${bg}; border-left: var(--conf-strip) solid ${brd}; padding:12px; border-radius:12px; margin-bottom:12px;">
                        <div style="flex:1; min-width:0;">
                            <div style="font-weight: 800; font-size: 18px; color:var(--text-main); margin-bottom:4px;">${single.name} ${single.id && single.id > 0 ? `(Sr. ${single.id})` : ''}</div>
                            <div style="font-size: 14px; color: var(--text-muted); margin-bottom:8px;">${single.address || 'No exact address'}</div>
                            <div style="font-size: 11px; font-weight: 700; color: ${brd}; text-transform:uppercase;">${txt}</div>
                        </div>
                        ${single.phone ? `<a href="tel:${single.phone}" style="background: var(--primary); color: white; width: 40px; height: 40px; min-width:40px; border-radius: 50%; display: flex; justify-content: center; align-items: center; text-decoration: none; margin-left:12px; box-shadow:0 2px 8px rgba(47,95,255,0.3);"><i class="fa-solid fa-phone" style="font-size:16px;"></i></a>` : ''}
                    </div>
                    `;
                }'''

new_group = '''                let subStopsHtml = '';
                if (stop.subStops && stop.subStops.length > 1) {
                    let actionableCount = stop.subStops.filter(ss => ss.status === 'PENDING' && ss.confirmation !== 'CANCELLED').length;
                    let cancelledCount = stop.subStops.filter(ss => ss.confirmation === 'CANCELLED').length;
                    let actionableTotal = stop.subStops.length - cancelledCount;
                    let headerText = `${actionableTotal} Customers \u00B7 ${actionableCount} left`;
                    if (cancelledCount > 0) headerText += ` \u00B7 ${cancelledCount} cancelled`;
                    
                    let sortedStops = [...stop.subStops].sort((a,b) => (a.confirmation==='CANCELLED' ? 1 : 0) - (b.confirmation==='CANCELLED' ? 1 : 0));
                    
                    subStopsHtml = `<div id="group-card-header" style="padding-bottom:8px;">
                        <div style="font-size: 13px; font-weight: 700; color: var(--primary); text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px;">${headerText}</div>
                    </div>
                    <div id="group-customer-list" style="overflow-y:auto; overscroll-behavior:contain; -webkit-overflow-scrolling:touch; max-height:min(calc(55dvh - 100px), calc(55vh - 100px)); display:flex; flex-direction:column; gap:6px; margin-bottom:8px;">
                        ${sortedStops.map((ss, i) => {
                            let isCanc = ss.confirmation === 'CANCELLED';
                            let isConf = ss.confirmation === 'CONFIRMED';
                            let bg = isCanc ? '#fef2f2' : (isConf ? '#ecfdf5' : '#eff6ff');
                            let brd = isCanc ? '#ef4444' : (isConf ? '#10b981' : '#2F5FFF');
                            let txt = isCanc ? 'Cancelled' : (isConf ? 'Confirmed' : 'Not confirmed');
                            return `
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; background:${bg}; border-left: var(--conf-strip) solid ${brd}; padding:8px 10px; border-radius:8px;">
                                <div style="flex:1; min-width:0;">
                                    <div style="font-weight: 700; font-size: 14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:var(--text-main); text-decoration:${isCanc?'line-through':'none'}; opacity:${isCanc?'0.6':'1'};">${ss.name} ${ss.id && ss.id > 0 ? `(Sr. ${ss.id})` : ''}</div>
                                    <div style="font-size: 12px; color: var(--text-muted); display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; margin-top:2px;">${ss.address || 'No exact address'}</div>
                                    <div style="font-size:10px; font-weight:700; margin-top:4px; color:${brd}; opacity:${isCanc?'0.8':'1'};">${txt}</div>
                                </div>
                                ${!isCanc && ss.phone ? `<a href="tel:${ss.phone}" style="background: var(--primary); color: white; width: 32px; height: 32px; min-width:32px; border-radius: 50%; display: flex; justify-content: center; align-items: center; text-decoration: none; margin-left:8px;"><i class="fa-solid fa-phone" style="font-size:13px;"></i></a>` : ''}
                            </div>
                        `;
                        }).join('')}
                    </div>`;
                } else {
                    let single = stop.subStops ? stop.subStops[0] : stop;
                    let isCanc = single.confirmation === 'CANCELLED';
                    let isConf = single.confirmation === 'CONFIRMED';
                    let bg = isCanc ? '#fef2f2' : (isConf ? '#ecfdf5' : '#eff6ff');
                    let brd = isCanc ? '#ef4444' : (isConf ? '#10b981' : '#2F5FFF');
                    let txt = isCanc ? 'Cancelled' : (isConf ? 'Confirmed' : 'Not confirmed');
                    
                    subStopsHtml = `
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; background:${bg}; border-left: var(--conf-strip) solid ${brd}; padding:12px; border-radius:12px; margin-bottom:12px;">
                        <div style="flex:1; min-width:0;">
                            <div style="font-weight: 800; font-size: 18px; color:var(--text-main); margin-bottom:4px; text-decoration:${isCanc?'line-through':'none'}; opacity:${isCanc?'0.6':'1'};">${single.name} ${single.id && single.id > 0 ? `(Sr. ${single.id})` : ''}</div>
                            <div style="font-size: 14px; color: var(--text-muted); margin-bottom:8px;">${single.address || 'No exact address'}</div>
                            <div style="font-size: 11px; font-weight: 700; color: ${brd}; text-transform:uppercase;">${txt}</div>
                        </div>
                        ${!isCanc && single.phone ? `<a href="tel:${single.phone}" style="background: var(--primary); color: white; width: 40px; height: 40px; min-width:40px; border-radius: 50%; display: flex; justify-content: center; align-items: center; text-decoration: none; margin-left:12px; box-shadow:0 2px 8px rgba(47,95,255,0.3);"><i class="fa-solid fa-phone" style="font-size:16px;"></i></a>` : ''}
                    </div>
                    `;
                }'''

text = text.replace(old_group, new_group)
with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
