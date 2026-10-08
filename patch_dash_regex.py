import io
import re

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add `let dynSr = 1;` before `truckRoute.forEach`
text = re.sub(r'if \(truckRoute\) \{\s*truckRoute\.forEach\(customerId => \{', r'if (truckRoute) {\n                    let dynSr = 1;\n                    truckRoute.forEach(customerId => {', text)

# 2. Add `let currentSr = isDepot ? "-" : dynSr++;` and change displayName
text = re.sub(r'let displayName = isDepot \? customer\.name : `Stop \$\{customer\.stop_number\}: \$\{customer\.name\}`;', r'let currentSr = isDepot ? "-" : dynSr++;\n                            let displayName = isDepot ? customer.name : `Stop ${currentSr}: ${customer.name}`;', text)

# 3. In manual override dropdown:
# opt.text = "After Stop " + s.stop_number + ": " + s.name;
# Change it to just use array index! Wait, how is the dropdown populated?
# It's populated by `data.customers.filter(c => c.truck_id === parseInt(selT))`
# We can do `let idx = 1;` and then `opt.text = "After Stop " + (idx++) + ": " + s.name;`

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
