import io

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_conf_html = '''                            let isConf = customer.confirmation === 'CONFIRMED';
                            let confHtml = isDepot ? '' : `<span style="font-size:10px; font-weight:700; padding:2px 6px; border-radius:8px; margin-left:8px; ${isConf ? 'background:#ecfdf5; color:#10b981; border:1px solid #10b981;' : 'background:#eff6ff; color:#2F5FFF; border:1px solid #2F5FFF;'}">${isConf ? 'CONFIRMED' : 'NOT CONFIRMED'}</span>`;'''

new_conf_html = '''                            let isConf = customer.confirmation === 'CONFIRMED';
                            let isCanc = customer.confirmation === 'CANCELLED';
                            let confHtml = isDepot ? '' : `<span style="font-size:10px; font-weight:700; padding:2px 6px; border-radius:8px; margin-left:8px; ${isConf ? 'background:#ecfdf5; color:#10b981; border:1px solid #10b981;' : (isCanc ? 'background:#fef2f2; color:#ef4444; border:1px solid #ef4444;' : 'background:#eff6ff; color:#2F5FFF; border:1px solid #2F5FFF;')}">${isConf ? 'CONFIRMED' : (isCanc ? 'CANCELLED' : 'NOT CONFIRMED')}</span>`;'''

text = text.replace(old_conf_html, new_conf_html)
with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
