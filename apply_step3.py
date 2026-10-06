import os
import re

filepath = 'waste_route_optimizer.py'
content = open(filepath, 'r', encoding='utf-8').read()

# I will write a regex substitution to find blocks setting "sequence": ... and add "confirmation": ... right after it.
# Wait, I need to know the customer object variable name for each block!

# 1. upload()
# "sequence": c.get('stop_number', None),
# "status": "PENDING"
content = re.sub(
    r'("sequence": c\.get\(\'stop_number\', None\),\s*)"status": "PENDING"',
    r'\1"status": "PENDING",\n                        "confirmation": c.get("confirmation", "NOT_CONFIRMED")',
    content
)

# 2. api/add_stop
# "sequence": target_sequence + 1,
# "status": "PENDING"
content = re.sub(
    r'("sequence": target_sequence \+ 1,\s*)"status": "PENDING"',
    r'\1"status": "PENDING",\n                    "confirmation": "NOT_CONFIRMED"',
    content
)

# 3. api/ai_rebalance
# "sequence": stop_num + 1,
# "status": "PENDING"
# Note: c is the customer object from `pending_customers`
content = re.sub(
    r'("sequence": stop_num \+ 1,\s*)"status": "PENDING"',
    r'\1"status": "PENDING",\n                        "confirmation": c.confirmation or "NOT_CONFIRMED"',
    content
)

# 4. api/ai_rebalance depot
# "sequence": len(route) + 1,
# "status": "PENDING"
content = re.sub(
    r'("sequence": len\(route\) \+ 1,\s*)"status": "PENDING"',
    r'\1"status": "PENDING",\n                "confirmation": "NOT_CONFIRMED"',
    content
)

# 5. /api/update_route_manual completed customers
# "sequence": c.stop_number,
# "status": "COMPLETED"
content = re.sub(
    r'("sequence": c\.stop_number,\s*)"status": "COMPLETED"',
    r'\1"status": "COMPLETED",\n                "confirmation": c.confirmation or "NOT_CONFIRMED"',
    content
)

# 6. /api/update_route_manual pending customers
# "sequence": idx + 1,
# "status": c.status
content = re.sub(
    r'("sequence": idx \+ 1,\s*)"status": c\.status',
    r'\1"status": c.status,\n                    "confirmation": c.confirmation or "NOT_CONFIRMED"',
    content
)

# 7. deploy_template
# "sequence": c.get('stop_number'),
# "status": "PENDING"
content = re.sub(
    r'("sequence": c\.get\(\'stop_number\'\),\s*)"status": "PENDING"',
    r'\1"status": "PENDING",\n                        "confirmation": c.get("confirmation", "NOT_CONFIRMED")',
    content
)

# 8. dynamic_recalculate
# "sequence": start_seq + seq,
# "status": "PENDING"
content = re.sub(
    r'("sequence": start_seq \+ seq,\s*)"status": "PENDING"',
    r'\1"status": "PENDING",\n                            "confirmation": cust.get("confirmation", "NOT_CONFIRMED")',
    content
)

# 9. dynamic_recalculate depot
# "sequence": start_seq + len(route),
# "status": "PENDING"
content = re.sub(
    r'("sequence": start_seq \+ len\(route\),\s*)"status": "PENDING"',
    r'\1"status": "PENDING",\n                    "confirmation": "NOT_CONFIRMED"',
    content
)

open(filepath, 'w', encoding='utf-8').write(content)
print("SUCCESS Step 3")
