import os

def process_driver_file(filepath):
    content = open(filepath, 'r', encoding='utf-8').read()
    
    # 1. CSS
    old_active = ".stop-item.active { background: #eff6ff; border: 1px solid #bfdbfe; }"
    new_active = ".stop-item.active { outline: 2px solid var(--primary); outline-offset: -2px; box-shadow: 0 4px 12px rgba(47, 95, 255, 0.15); }"
    content = content.replace(old_active, new_active)
    
    # 2. Add Legend to Stop List Header
    old_header = """                  document.getElementById('bottom-sheet').innerHTML = `
                      <div class="drag-handle"></div>
                      <h2 style="margin-top:0; font-size:18px; margin-bottom:16px;">Upcoming Stops</h2>"""
    new_header = """                  document.getElementById('bottom-sheet').innerHTML = `
                      <div class="drag-handle"></div>
                      <h2 style="margin-top:0; font-size:18px; margin-bottom:6px;">Upcoming Stops</h2>
                      <div style="display:flex; gap:12px; margin-bottom:16px; font-size:12px; font-weight:600;">
                          <div style="display:flex; align-items:center; gap:4px;"><span style="width:10px;height:10px;border-radius:3px;background:#ecfdf5;border-left:2px solid #10b981;"></span> Confirmed</div>
                          <div style="display:flex; align-items:center; gap:4px;"><span style="width:10px;height:10px;border-radius:3px;background:#eff6ff;border-left:2px solid #2F5FFF;"></span> Not confirmed</div>
                      </div>"""
    content = content.replace(old_header, new_header)
    
    # 3. Helper for background styles
    # We will insert a helper function right inside render()
    helper = """
                function getConfStyle(conf) {
                    if (conf === 'CONFIRMED') return { bg: '#ecfdf5', border: '#10b981', text: 'Confirmed', color: '#047857' };
                    return { bg: '#eff6ff', border: '#2F5FFF', text: 'Not confirmed', color: '#1d4ed8' };
                }"""
    
    # Wait, let's just do it directly.
    # Current Stop main view:
    old_curr = """                  if (stop.subStops && stop.subStops.length > 1) {
                      let pendingSubStops = stop.subStops.filter(ss => ss.status === 'PENDING');
                      
                      subStopsHtml = `
                          <div style="font-size: 13px; font-weight: 700; color: var(--primary); text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">${stop.subStops.length} Customers at this Location:</div>
                          <div style="display:flex; flex-direction:column; background:#f8fafc; padding:12px; border-radius:12px; border:1px solid var(--border);">"""
                          
    new_curr = """                  if (stop.subStops && stop.subStops.length > 1) {
                      let pendingSubStops = stop.subStops.filter(ss => ss.status === 'PENDING');
                      
                      subStopsHtml = `
                          <div style="font-size: 13px; font-weight: 700; color: var(--primary); text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">${stop.subStops.length} Customers at this Location:</div>
                          <div style="display:flex; flex-direction:column; gap:8px;">"""
    content = content.replace(old_curr, new_curr)
    
    # Sub-stops inside grouped stops
    old_sub = """                              ${stop.subStops.map((ss, i) => `
                                  <div style="display: flex; justify-content: space-between; align-items: flex-start; ${i !== stop.subStops.length - 1 ? 'border-bottom:1px solid #e2e8f0; padding-bottom:12px; margin-bottom:12px;' : ''}">
                                      <div style="flex:1;">
                                          <div style="font-weight: 700; font-size: 16px; margin-bottom: 4px; color:var(--text-main);">${ss.name} ${ss.id && ss.id > 0 ? `(Sr. ${ss.id})` : ''}</div>
                                          <div style="font-size: 13px; color: var(--text-muted); line-height:1.4;"><i class="fa-solid fa-house" style="margin-right:6px; opacity:0.7;"></i>${ss.address || 'No exact address'}</div>
                                      </div>"""
    
    new_sub = """                              ${stop.subStops.map((ss, i) => {
                                  let cConf = ss.confirmation === 'CONFIRMED';
                                  let bg = cConf ? '#ecfdf5' : '#eff6ff';
                                  let brd = cConf ? '#10b981' : '#2F5FFF';
                                  let txt = cConf ? 'Confirmed' : 'Not confirmed';
                                  return `
                                  <div style="display: flex; justify-content: space-between; align-items: flex-start; background:${bg}; border-left:4px solid ${brd}; padding:12px; border-radius:8px;">
                                      <div style="flex:1;">
                                          <div style="font-weight: 700; font-size: 16px; margin-bottom: 4px; color:var(--text-main);">${ss.name} ${ss.id && ss.id > 0 ? `(Sr. ${ss.id})` : ''}</div>
                                          <div style="font-size: 13px; color: var(--text-muted); line-height:1.4;"><i class="fa-solid fa-house" style="margin-right:6px; opacity:0.7;"></i>${ss.address || 'No exact address'}</div>
                                          <div style="font-size:10px; font-weight:700; margin-top:6px; color:${brd};">${txt}</div>
                                      </div>`;
                              }).join('')}"""
    content = content.replace(old_sub, new_sub)
    
    # Sub-stops closing div fix (since we removed the wrapper div styling)
    content = content.replace("</div>\n                          <div id=\"skipRadioGroup\">", "</div>\n                          <div id=\"skipRadioGroup\">")
    
    # Single stop main view coloring
    old_single = """                  } else {
                      subStopsHtml = `
                          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                              <div class="stop-name" style="margin-bottom: 0;">${stop.name} ${stop.id && stop.id > 0 ? `(Sr. ${stop.id})` : ''}</div>"""
                              
    new_single = """                  } else {
                      let cConf = stop.confirmation === 'CONFIRMED';
                      let bg = cConf ? '#ecfdf5' : '#eff6ff';
                      let brd = cConf ? '#10b981' : '#2F5FFF';
                      let txt = cConf ? 'Confirmed' : 'Not confirmed';
                      subStopsHtml = `
                          <div style="margin-bottom:12px; background:${bg}; border-left:4px solid ${brd}; padding:12px; border-radius:8px;">
                          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                              <div class="stop-name" style="margin-bottom: 0;">${stop.name} ${stop.id && stop.id > 0 ? `(Sr. ${stop.id})` : ''}</div>"""
    content = content.replace(old_single, new_single)
    
    old_single_close = """                              <i class="fa-solid fa-location-dot" style="margin-top:4px;"></i>
                              <span>${stop.address || 'No address provided'}</span>
                          </div>
                      `;
                  }"""
                  
    new_single_close = """                              <i class="fa-solid fa-location-dot" style="margin-top:4px;"></i>
                              <span>${stop.address || 'No address provided'}</span>
                          </div>
                          <div style="font-size:10px; font-weight:700; margin-top:6px; color:${brd};">${txt}</div>
                          </div>
                      `;
                  }"""
    content = content.replace(old_single_close, new_single_close)
    
    # Stop List coloring
    old_list = """                  return `
                      <div class="${classes}">
                          ${icon}
                          <div>
                              <div style="font-weight:600;">${titleText}</div>
                              <div style="font-size:12px; color:var(--text-muted);">${s.address}</div>
                          </div>
                      </div>
                  `;"""
                  
    new_list = """                  let confStyle = '';
                  let badgeHtml = '';
                  if (!isDepot) {
                      if (s.subStops && s.subStops.length > 1) {
                          let cCount = s.subStops.filter(x => x.confirmation === 'CONFIRMED').length;
                          let nCount = s.subStops.length - cCount;
                          if (nCount === 0) {
                              confStyle = 'background:#ecfdf5; border-left:4px solid #10b981;';
                              badgeHtml = '<div style="font-size:10px; font-weight:700; margin-top:4px; color:#10b981;">Confirmed</div>';
                          } else if (cCount === 0) {
                              confStyle = 'background:#eff6ff; border-left:4px solid #2F5FFF;';
                              badgeHtml = '<div style="font-size:10px; font-weight:700; margin-top:4px; color:#2F5FFF;">Not confirmed</div>';
                          } else {
                              confStyle = 'background: linear-gradient(90deg, #ecfdf5 50%, #eff6ff 50%); border-left:4px solid #10b981; border-right:4px solid #2F5FFF;';
                              badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:var(--text-main);">${cCount} confirmed &middot; ${nCount} not</div>`;
                          }
                      } else {
                          let cConf = s.confirmation === 'CONFIRMED';
                          let bg = cConf ? '#ecfdf5' : '#eff6ff';
                          let brd = cConf ? '#10b981' : '#2F5FFF';
                          let txt = cConf ? 'Confirmed' : 'Not confirmed';
                          confStyle = `background:${bg}; border-left:4px solid ${brd};`;
                          badgeHtml = `<div style="font-size:10px; font-weight:700; margin-top:4px; color:${brd};">${txt}</div>`;
                      }
                  }
                  
                  return `
                      <div class="${classes}" style="${confStyle}">
                          ${icon}
                          <div>
                              <div style="font-weight:600;">${titleText}</div>
                              <div style="font-size:12px; color:var(--text-muted);">${s.address}</div>
                              ${badgeHtml}
                          </div>
                      </div>
                  `;"""
    content = content.replace(old_list, new_list)
    
    open(filepath, 'w', encoding='utf-8').write(content)

process_driver_file('templates/driver_view.html')
process_driver_file('src/index.html')

print("SUCCESS Step 7")
