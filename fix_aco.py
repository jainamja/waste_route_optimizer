content = open('aco_vrp.py', 'rb').read().decode('utf-8').replace('\r\n', '\n')

old_constraint = '''        # To guarantee we find a solution within 8 seconds, we use extremely relaxed bounds.
        # We enforce a strict minimum of 1 customer per truck to ensure no truck is left empty.
        min_stops = 1
        # Maximum is theoretically all customers, leaving room for the AI to dynamically balance based on Time
        max_stops = len(self.customers)
        
        for vehicle_id in range(self.num_trucks):
            # We add +1 because the End node itself increments the CumulVar by 1.
            stops_dimension.CumulVar(routing.End(vehicle_id)).SetRange(min_stops + 1, max_stops + 1)'''

new_constraint = '''        # Maximum is theoretically all customers, leaving room for the AI to dynamically balance based on Time
        max_stops = len(self.customers)
        
        for vehicle_id in range(self.num_trucks):
            # Min stops is 0, allowing the AI to leave trucks empty if not needed
            stops_dimension.CumulVar(routing.End(vehicle_id)).SetRange(0, max_stops + 1)'''

content = content.replace(old_constraint, new_constraint)
open('aco_vrp.py', 'w', newline='\r\n', encoding='utf-8').write(content)
print("SUCCESS")
