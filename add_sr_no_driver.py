import os

def process_file(filepath):
    content = open(filepath, 'r', encoding='utf-8').read()
    
    # 1. Single Stop Main View
    old1 = """<div class="stop-name" style="margin-bottom: 0;">${stop.name}</div>"""
    new1 = """<div class="stop-name" style="margin-bottom: 0;">${stop.name} ${stop.id && stop.id > 0 ? `(Sr. ${stop.id})` : ''}</div>"""
    content = content.replace(old1, new1)
    
    # 2. Grouped Stops Sub-Stops Main View
    old2 = """<div style="font-weight: 700; font-size: 16px; margin-bottom: 4px; color:var(--text-main);">${ss.name}</div>"""
    new2 = """<div style="font-weight: 700; font-size: 16px; margin-bottom: 4px; color:var(--text-main);">${ss.name} ${ss.id && ss.id > 0 ? `(Sr. ${ss.id})` : ''}</div>"""
    content = content.replace(old2, new2)
    
    # 3. Stop List titleText
    old3 = """let titleText = isDepot ? s.name : `Stop ${displaySeq}: ${s.name}`;"""
    new3 = """let titleText = isDepot ? s.name : `Stop ${displaySeq}: ${s.name} ${s.id && s.id > 0 ? `(Sr. ${s.id})` : ''}`;"""
    content = content.replace(old3, new3)
    
    open(filepath, 'w', encoding='utf-8').write(content)

process_file('templates/driver_view.html')
process_file('src/index.html')

print("SUCCESS")
