import os

def process_driver_file(filepath):
    content = open(filepath, 'r', encoding='utf-8').read()
    
    old_skip = """                              ${pendingSubStops.map(ss => `
                                  <label style="display:flex; align-items:center; padding:15px; border:1px solid #e5e7eb; border-radius:12px; margin-bottom:10px; gap:15px;">"""
    
    new_skip = """                              ${pendingSubStops.map(ss => {
                                  let cConf = ss.confirmation === 'CONFIRMED';
                                  let bg = cConf ? '#ecfdf5' : '#eff6ff';
                                  let brd = cConf ? '#10b981' : '#2F5FFF';
                                  let txt = cConf ? 'Confirmed' : 'Not confirmed';
                                  return `
                                  <label style="display:flex; align-items:center; padding:15px; border:1px solid ${brd}; background:${bg}; border-left:4px solid ${brd}; border-radius:12px; margin-bottom:10px; gap:15px;">"""
    content = content.replace(old_skip, new_skip)
    
    old_skip_close = """                                      <div style="flex:1;">
                                          <div style="font-weight:600; font-size:16px;">${ss.name} ${ss.id && ss.id > 0 ? `(Sr. ${ss.id})` : ''}</div>
                                          <div style="font-size:14px; color:var(--text-secondary); margin-top:4px;">${ss.address}</div>
                                      </div>
                                  </label>
                              `).join('')}"""
                              
    new_skip_close = """                                      <div style="flex:1;">
                                          <div style="font-weight:600; font-size:16px;">${ss.name} ${ss.id && ss.id > 0 ? `(Sr. ${ss.id})` : ''}</div>
                                          <div style="font-size:14px; color:var(--text-secondary); margin-top:4px;">${ss.address}</div>
                                          <div style="font-size:10px; font-weight:700; margin-top:6px; color:${brd};">${txt}</div>
                                      </div>
                                  </label>
                              `;
                              }).join('')}"""
    content = content.replace(old_skip_close, new_skip_close)

    open(filepath, 'w', encoding='utf-8').write(content)

process_driver_file('templates/driver_view.html')
process_driver_file('src/index.html')

print("SUCCESS Step 8")
