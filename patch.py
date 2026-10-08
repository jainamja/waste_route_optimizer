import io

with io.open('templates/live_tracking.html', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('let skipList = [], leftList = [];', 'let skipList = [], leftList = [], compList = [];')
text = text.replace("if (s.status === 'COMPLETED') tComp++;", "if (s.status === 'COMPLETED') { tComp++; compList.push(s); }")

html_to_inject = '''<div class="t-stats">${statsStr}</div>
                        ${(() => {
                            let lastStop = compList.length > 0 ? compList[compList.length - 1] : null;
                            let nextStop = leftList.length > 0 ? leftList[0] : null;
                            if (tTotal === 0 || (!lastStop && !nextStop)) return '';
                            let html = '<div style="background:#f8fafc; border-radius:8px; padding:10px; margin-top:12px; border:1px solid #e2e8f0;">';
                            if (lastStop) {
                                html += '<div style="font-size:11px; font-weight:700; color:#10b981; text-transform:uppercase; margin-bottom:2px;">Last Completed</div>';
                                html += '<div style="font-size:13px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-bottom:' + (nextStop?'8px':'0') + ';">' + lastStop.name + '</div>';
                            }
                            if (nextStop) {
                                html += '<div style="font-size:11px; font-weight:700; color:var(--primary); text-transform:uppercase; margin-bottom:2px;">Upcoming</div>';
                                html += '<div style="font-size:13px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' + nextStop.name + ' <span style="font-size:11px; color:var(--text-muted);">#' + (nextStop.sequence||nextStop.stop_number) + '</span></div>';
                            }
                            html += '</div>';
                            return html;
                        })()}'''

text = text.replace('<div class="t-stats">${statsStr}</div>', html_to_inject)

with io.open('templates/live_tracking.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
