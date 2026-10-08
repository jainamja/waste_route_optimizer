import io

with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_stop = "let titleText = isDepot ? s.name : `Stop ${displaySeq}: ${s.name} ${s.dynamicSr ? `(Sr. ${s.dynamicSr})` : ''}`;"
new_stop = "let titleText = isDepot ? s.name : `Stop ${s.dynamicSr}: ${s.name} ${s.dynamicSr ? `(Sr. ${s.dynamicSr})` : ''}`;"
text = text.replace(old_stop, new_stop)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
