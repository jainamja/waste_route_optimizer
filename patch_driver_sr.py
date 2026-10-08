import io
import re

with io.open('templates/driver_view.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace all occurrences of `(Sr. ${some_var.id})` with `(Sr. ${some_var.dynamicSr})`
# The exact string is usually: `${some_var.id && some_var.id > 0 ? \`(Sr. ${some_var.id})\` : ''}`

def replacer(match):
    var_name = match.group(1)
    return f"${{{var_name}.dynamicSr ? `(Sr. ${{{var_name}.dynamicSr}})` : ''}}"

pattern = r"\$\{\s*([a-zA-Z0-9_]+)\.id\s*&&\s*\1\.id\s*>\s*0\s*\?\s*`\(Sr\.\s*\$\{\1\.id\}\)`\s*:\s*''\s*\}"

new_text, count = re.subn(pattern, replacer, text)

# Also check for Stop ${displaySeq}
old_stop = "let titleText = isDepot ? s.name : `Stop ${displaySeq}: ${s.name} ${s.id && s.id > 0 ? `(Sr. ${s.id})` : ''}`;"
new_stop = "let titleText = isDepot ? s.name : `Stop ${s.dynamicSr}: ${s.name} ${s.dynamicSr ? `(Sr. ${s.dynamicSr})` : ''}`;"
new_text = new_text.replace(old_stop, new_stop)

with io.open('templates/driver_view.html', 'w', encoding='utf-8', newline='') as f:
    f.write(new_text)
print("Replaced:", count)
