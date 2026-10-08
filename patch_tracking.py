import io

with io.open('templates/live_tracking.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update variables
old_vars = '''                let tTotal = stops.length;
                let tComp = 0, tSkip = 0, tLeft = 0, tNotConf = 0;
                let skipList = [], leftList = [], compList = [];
                
                stops.forEach(s => {
                    if (s.status === 'COMPLETED') { tComp++; compList.push(s); }
                    else if (s.status === 'SKIPPED') { tSkip++; skipList.push(s); }
                    else {
                        tLeft++;
                        if (leftList.length < 5) leftList.push(s);
                        if (s.confirmation === 'NOT_CONFIRMED') tNotConf++;
                    }
                });'''

new_vars = '''                let tTotal = stops.length;
                let tComp = 0, tSkip = 0, tCanc = 0, tLeft = 0, tNotConf = 0;
                let skipList = [], leftList = [], compList = [], cancList = [];
                
                stops.forEach(s => {
                    if (s.confirmation === 'CANCELLED') { tCanc++; cancList.push(s); }
                    else if (s.status === 'COMPLETED') { tComp++; compList.push(s); }
                    else if (s.status === 'SKIPPED') { tSkip++; skipList.push(s); }
                    else {
                        tLeft++;
                        if (leftList.length < 5) leftList.push(s);
                        if (s.confirmation === 'NOT_CONFIRMED') tNotConf++;
                    }
                });'''
text = text.replace(old_vars, new_vars)

# 2. Update stats string
old_stats = '''                    statsStr = `${tComp} done &middot; ${tSkip} skipped &middot; ${tLeft} left`;
                    if (tNotConf > 0) statsStr += ` <span class="t-stats-muted">(${tNotConf} not confirmed)</span>`;'''
new_stats = '''                    statsStr = `${tComp} done &middot; ${tSkip} skipped &middot; ${tCanc} cancelled &middot; ${tLeft} left`;
                    if (tNotConf > 0) statsStr += ` <span class="t-stats-muted">(${tNotConf} not confirmed)</span>`;'''
text = text.replace(old_stats, new_stats)

# 3. Update fleet accumulation
old_fleet = '''            let fleetTotal = 0, fleetComp = 0, fleetSkip = 0;'''
new_fleet = '''            let fleetTotal = 0, fleetComp = 0, fleetSkip = 0, fleetCanc = 0;'''
text = text.replace(old_fleet, new_fleet)

old_accum = '''                fleetTotal += tTotal;
                fleetComp += tComp;
                fleetSkip += tSkip;'''
new_accum = '''                fleetTotal += tTotal;
                fleetComp += tComp;
                fleetSkip += tSkip;
                fleetCanc += tCanc;'''
text = text.replace(old_accum, new_accum)

# 4. Update fleet summary
old_summary = '''            let fleetLeft = fleetTotal - fleetComp - fleetSkip;
            let fleetPct = fleetTotal > 0 ? Math.round((fleetComp / fleetTotal) * 100) : 0;
            
            document.getElementById('fleet-summary').innerHTML = `
                <div class="fleet-stat">
                    <div class="fleet-stat-val" style="color:#10b981;">${fleetComp}</div>
                    <div class="fleet-stat-label">Done</div>
                </div>
                <div class="fleet-stat">
                    <div class="fleet-stat-val" style="color:#ef4444;">${fleetSkip}</div>
                    <div class="fleet-stat-label">Skip</div>
                </div>
                <div class="fleet-stat">
                    <div class="fleet-stat-val">${fleetLeft}</div>
                    <div class="fleet-stat-label">Left</div>
                </div>
                <div class="fleet-stat">
                    <div class="fleet-stat-val" style="color:var(--primary);">${fleetPct}%</div>
                    <div class="fleet-stat-label">Progress</div>
                </div>
            `;'''

new_summary = '''            let fleetLeft = fleetTotal - fleetComp - fleetSkip - fleetCanc;
            let fleetPct = fleetTotal > 0 ? Math.round((fleetComp / fleetTotal) * 100) : 0;
            
            document.getElementById('fleet-summary').innerHTML = `
                <div class="fleet-stat">
                    <div class="fleet-stat-val" style="color:#10b981;">${fleetComp}</div>
                    <div class="fleet-stat-label">Done</div>
                </div>
                <div class="fleet-stat">
                    <div class="fleet-stat-val" style="color:#ef4444;">${fleetSkip}</div>
                    <div class="fleet-stat-label">Skip</div>
                </div>
                <div class="fleet-stat" title="Cancelled">
                    <div class="fleet-stat-val" style="color:#f87171;">${fleetCanc}</div>
                    <div class="fleet-stat-label">Canc</div>
                </div>
                <div class="fleet-stat">
                    <div class="fleet-stat-val">${fleetLeft}</div>
                    <div class="fleet-stat-label">Left</div>
                </div>
                <div class="fleet-stat">
                    <div class="fleet-stat-val" style="color:var(--primary);">${fleetPct}%</div>
                    <div class="fleet-stat-label">Progress</div>
                </div>
            `;'''

text = text.replace(old_summary, new_summary)

# 5. Add cancelled bar to prog-bar-wrap and fleet-prog-bar
old_prog = '''                        <div class="prog-bar-wrap" style="${progStyle} margin-top:8px;">
                            <div class="prog-bar-comp" style="width: ${pctComp}%"></div>
                            <div class="prog-bar-skip" style="width: ${pctSkip}%"></div>
                        </div>'''
new_prog = '''                        <div class="prog-bar-wrap" style="${progStyle} margin-top:8px;">
                            <div class="prog-bar-comp" style="width: ${pctComp}%"></div>
                            <div class="prog-bar-skip" style="width: ${pctSkip}%"></div>
                            <div class="prog-bar-canc" style="width: ${tTotal>0?(tCanc/tTotal)*100:0}%; background:#fca5a5;"></div>
                        </div>'''
text = text.replace(old_prog, new_prog)

old_fleet_prog = '''            document.getElementById('fleet-prog-bar').innerHTML = `
                <div class="prog-bar-comp" style="width: ${fleetTotal > 0 ? (fleetComp/fleetTotal)*100 : 0}%"></div>
                <div class="prog-bar-skip" style="width: ${fleetTotal > 0 ? (fleetSkip/fleetTotal)*100 : 0}%"></div>
            `;'''
new_fleet_prog = '''            document.getElementById('fleet-prog-bar').innerHTML = `
                <div class="prog-bar-comp" style="width: ${fleetTotal > 0 ? (fleetComp/fleetTotal)*100 : 0}%"></div>
                <div class="prog-bar-skip" style="width: ${fleetTotal > 0 ? (fleetSkip/fleetTotal)*100 : 0}%"></div>
                <div class="prog-bar-canc" style="width: ${fleetTotal > 0 ? (fleetCanc/fleetTotal)*100 : 0}%; background:#fca5a5;"></div>
            `;'''
text = text.replace(old_fleet_prog, new_fleet_prog)

with io.open('templates/live_tracking.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
