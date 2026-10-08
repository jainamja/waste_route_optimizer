import io
with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_btn = '''                    <div class="action-buttons" style="position:sticky; bottom:0; background:var(--card-bg); padding-top:8px;">
                        <button class="btn btn-success" onclick="markStop('COMPLETED')">
                            <i class="fa-solid fa-check"></i> ${isLast ? 'Finish' : ((stop.subStops && stop.subStops.length > 1) ? `Complete ${stop.subStops.filter(ss => ss.status === 'PENDING').length} & Next` : 'Complete & Next')}
                        </button>
                        <button class="btn btn-danger" onclick="markStop('SKIPPED')">
                            <i class="fa-solid fa-forward-step"></i> Skip
                        </button>
                    </div>'''

new_btn = '''                    <div class="action-buttons" style="position:sticky; bottom:0; background:var(--card-bg); padding-top:8px;">
                        <button class="btn btn-success" onclick="markStop('COMPLETED')">
                            <i class="fa-solid fa-check"></i> ${isLast ? 'Finish' : ((stop.subStops && stop.subStops.length > 1) ? `Complete ${stop.subStops.filter(ss => ss.status === 'PENDING' && ss.confirmation !== 'CANCELLED').length} & Next` : 'Complete & Next')}
                        </button>
                        <button class="btn btn-danger" onclick="markStop('SKIPPED')">
                            <i class="fa-solid fa-forward-step"></i> Skip
                        </button>
                    </div>'''

text = text.replace(old_btn, new_btn)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print('Done!')
