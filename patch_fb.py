import io
import re

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace dict creations in save_template
old_save = """        'confirmation': c.confirmation if c.confirmation else 'NOT_CONFIRMED'
    } for c in cust_rows]"""
new_save = """        'confirmation': c.confirmation if c.confirmation else 'NOT_CONFIRMED',
        'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE'
    } for c in cust_rows]"""
text = text.replace(old_save, new_save)

old_dl = """                'confirmation': c.confirmation or 'NOT_CONFIRMED',
                'truck_id': None,"""
new_dl = """                'confirmation': c.confirmation or 'NOT_CONFIRMED',
                'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE',
                'truck_id': None,"""
text = text.replace(old_dl, new_dl)

# Let's use regex to append "customer_status": c.customer_status wherever "confirmation": c.confirmation or "NOT_CONFIRMED" is found
# Cases to handle:
# 1. c.get("confirmation", "NOT_CONFIRMED")
# 2. c.confirmation or "NOT_CONFIRMED"
# 3. "NOT_CONFIRMED"
# 4. "CANCELLED"
# 5. cust.get("confirmation", "NOT_CONFIRMED")

# Actually it's easier to just do it manually for all occurrences.
# Let's just find and replace in chunks.

old_1 = """                        "status": "PENDING",
                        "confirmation": c.get("confirmation", "NOT_CONFIRMED")
                    }"""
new_1 = """                        "status": "PENDING",
                        "confirmation": c.get("confirmation", "NOT_CONFIRMED"),
                        "customer_status": c.get("customer_status", "ACTIVE")
                    }"""
text = text.replace(old_1, new_1)

old_2 = """                    "status": "PENDING",
                    "confirmation": "NOT_CONFIRMED"
                }
                
                requests.put(f"{firebase_url}/routes/{route_key}/stops.json?auth={id_token}", json=stops)"""
new_2 = """                    "status": "PENDING",
                    "confirmation": "NOT_CONFIRMED",
                    "customer_status": "ACTIVE"
                }
                
                requests.put(f"{firebase_url}/routes/{route_key}/stops.json?auth={id_token}", json=stops)"""
text = text.replace(old_2, new_2)

old_3 = """                        "status": "PENDING",
                        "confirmation": c.confirmation or "NOT_CONFIRMED"
                    }"""
new_3 = """                        "status": "PENDING",
                        "confirmation": c.confirmation or "NOT_CONFIRMED",
                        "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
                    }"""
text = text.replace(old_3, new_3)

old_4 = """                    "status": c.status,
                    "confirmation": "CANCELLED"
                }"""
new_4 = """                    "status": c.status,
                    "confirmation": "CANCELLED",
                    "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
                }"""
text = text.replace(old_4, new_4)

old_5 = """                "status": "PENDING",
                "confirmation": "NOT_CONFIRMED"
            }"""
new_5 = """                "status": "PENDING",
                "confirmation": "NOT_CONFIRMED",
                "customer_status": "ACTIVE"
            }"""
text = text.replace(old_5, new_5)

old_6 = """                "status": "COMPLETED",
                "confirmation": c.confirmation or "NOT_CONFIRMED"
            }"""
new_6 = """                "status": "COMPLETED",
                "confirmation": c.confirmation or "NOT_CONFIRMED",
                "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
            }"""
text = text.replace(old_6, new_6)

old_7 = """                    "status": c.status,
                    "confirmation": c.confirmation or "NOT_CONFIRMED"
                }"""
new_7 = """                    "status": c.status,
                    "confirmation": c.confirmation or "NOT_CONFIRMED",
                    "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
                }"""
text = text.replace(old_7, new_7)

old_8 = """                            "status": "PENDING",
                            "confirmation": cust.get("confirmation", "NOT_CONFIRMED")
                        }"""
new_8 = """                            "status": "PENDING",
                            "confirmation": cust.get("confirmation", "NOT_CONFIRMED"),
                            "customer_status": cust.get("customer_status", "ACTIVE") or "ACTIVE"
                        }"""
text = text.replace(old_8, new_8)

old_9 = """                            "status": c.get('status', 'PENDING'),
                            "confirmation": "CANCELLED"
                        }"""
new_9 = """                            "status": c.get('status', 'PENDING'),
                            "confirmation": "CANCELLED",
                            "customer_status": getattr(c, "customer_status", "ACTIVE") if not isinstance(c, dict) else c.get("customer_status", "ACTIVE")
                        }"""
text = text.replace(old_9, new_9)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done!")
