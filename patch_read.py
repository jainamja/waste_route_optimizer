import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_read_append = """                    'location_url': loc_url_clean,
                    'lat': lat,
                    'lng': lng,
                    'status': 'PENDING'
                })"""
new_read_append = """                    'location_url': loc_url_clean,
                    'lat': lat,
                    'lng': lng,
                    'status': 'PENDING',
                    'customer_status': 'ACTIVE'
                })"""
text = text.replace(old_read_append, new_read_append)

old_pending_append_fb = """                                'phone': stop_info.get('phone', ''),
                                'lat': float(stop_info['lat']),
                                'lng': float(stop_info['lng']),
                                'confirmation': stop_info.get('confirmation', 'NOT_CONFIRMED'),
                                'truck_id': truck_id,
                                'status': stop_info.get('status', 'PENDING')
                            })"""
new_pending_append_fb = """                                'phone': stop_info.get('phone', ''),
                                'lat': float(stop_info['lat']),
                                'lng': float(stop_info['lng']),
                                'confirmation': stop_info.get('confirmation', 'NOT_CONFIRMED'),
                                'customer_status': stop_info.get('customer_status', 'ACTIVE'),
                                'truck_id': truck_id,
                                'status': stop_info.get('status', 'PENDING')
                            })"""
text = text.replace(old_pending_append_fb, new_pending_append_fb)

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done!")
