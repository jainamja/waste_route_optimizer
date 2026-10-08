import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_truck_stats = '''                if (!trucksInfo[t]) trucksInfo[t] = { total: 0, completed: 0, confirmed: 0, realCount: 0 };
                trucksInfo[t].total++;
                if (c.status === 'COMPLETED') trucksInfo[t].completed++;
                
                if (c.id > -1000) {
                    trucksInfo[t].realCount++;
                    if (c.confirmation === 'CONFIRMED') trucksInfo[t].confirmed++;
                }'''

new_truck_stats = '''                if (!trucksInfo[t]) trucksInfo[t] = { total: 0, completed: 0, confirmed: 0, cancelled: 0, realCount: 0 };
                trucksInfo[t].total++;
                if (c.status === 'COMPLETED') trucksInfo[t].completed++;
                
                if (c.id > -1000) {
                    trucksInfo[t].realCount++;
                    if (c.confirmation === 'CONFIRMED') trucksInfo[t].confirmed++;
                    if (c.confirmation === 'CANCELLED') trucksInfo[t].cancelled++;
                }'''

text = text.replace(old_truck_stats, new_truck_stats)

old_truck_html = '''<span style="font-size:12px; font-weight:600; padding:2px 8px; border-radius:12px; background:#f1f5f9; color:var(--text-main);">${info.confirmed} confirmed &middot; ${info.realCount - info.confirmed} not</span>'''
new_truck_html = '''<span style="font-size:12px; font-weight:600; padding:2px 8px; border-radius:12px; background:#f1f5f9; color:var(--text-main);">${info.confirmed} confirmed &middot; ${info.realCount - info.confirmed - info.cancelled} not &middot; ${info.cancelled} cancelled</span>'''

text = text.replace(old_truck_html, new_truck_html)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
