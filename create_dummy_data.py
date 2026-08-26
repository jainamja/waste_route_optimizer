import pandas as pd
import random

# Generate 20 customers around Ahmedabad, India
data = []
for i in range(1, 21):
    lat = 23.0 + random.uniform(-0.05, 0.05)
    lng = 72.57 + random.uniform(-0.05, 0.05)
    
    data.append({
        'Customer Name': f"Customer {i}",
        'Phone Number': f"987654{i:04d}",
        'Address': f"Address {i}, Ahmedabad",
        'Coordinates': f"{lat}, {lng}"
    })

df = pd.DataFrame(data)
df.to_excel('customers.xlsx', index=False)
print("customers.xlsx generated successfully.")
