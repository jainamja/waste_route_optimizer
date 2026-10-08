import io
import re

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_loop = """                if (truckRoute) {
                    truckRoute.forEach(customerId => {
                        let customer = data.customers.find(c => c.id === customerId);
                        if (customer) {
                            waypoints.push(`${customer.lat},${customer.lng}`);
                            let isDone = customer.status === 'COMPLETED';
                            let isDepot = customer.id < 0 || customer.name === 'End Location / Depot';
                            let displayName = isDepot ? customer.name : `Stop ${customer.stop_number}: ${customer.name}`;"""
new_loop = """                if (truckRoute) {
                    let dynSr = 1;
                    truckRoute.forEach(customerId => {
                        let customer = data.customers.find(c => c.id === customerId);
                        if (customer) {
                            waypoints.push(`${customer.lat},${customer.lng}`);
                            let isDone = customer.status === 'COMPLETED';
                            let isDepot = customer.id < 0 || customer.name === 'End Location / Depot';
                            let currentSr = isDepot ? '-' : dynSr++;
                            let displayName = isDepot ? customer.name : `Stop ${currentSr}: ${customer.name}`;"""
text = text.replace(old_loop, new_loop)

# Now remove (Sr. ${c.id}) and replace with (Sr. ${currentSr})
# Wait, in live_dashboard.html we don't have (Sr. ${c.id}) in the `displayName` variable!
# It's at `${displayName}${confHtml}` ... wait, where was `(Sr. ${c.id})`? Let's check my grep output earlier.
