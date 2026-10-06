import pandas as pd
import io
import re

dummy_csv = "Sr,Name,Address,Lat,Lng\\n1,Cust 1,Address 1,23.0225,72.5714\\n2,Cust 2,Address 2,23.03,72.58"
df = pd.read_csv(io.StringIO(dummy_csv))

cols = [str(c).lower() for c in df.columns]
df.columns = cols

coord_col = next((c for c in cols if 'coord' in c or ('lat' in c and 'lon' in c) or ('lat' in c and 'lng' in c)), None)
lat_col = next((c for c in cols if 'lat' in c), None) if not coord_col else None
lng_col = next((c for c in cols if 'lng' in c or 'lon' in c), None) if not coord_col else None

sr_no_col = next((c for c in cols if 'sr' in c or 'serial' in c or 'no.' in c or c == 'id'), None)
name_col = next((c for c in cols if 'name' in c), None)
phone_col = next((c for c in cols if 'phone' in c or 'mobile' in c or 'contact' in c), None)
address_col = next((c for c in cols if 'address' in c or 'society' in c or 'location' in c), None)

customers = []
for idx, row in df.iterrows():
    lat, lng = None, None
    if lat is None or lng is None:
        if coord_col: pass
        elif lat_col and lng_col: lat, lng = row[lat_col], row[lng_col]
        
    try:
        try:
            sr_id = int(row[sr_no_col]) if sr_no_col and not pd.isna(row[sr_no_col]) else idx + 1
        except:
            sr_id = idx + 1

        lat, lng = float(lat), float(lng)
        print(f"Row {idx}: Lat={lat}, Lng={lng}, isna={pd.isna(lat)}")
        if not pd.isna(lat) and not pd.isna(lng):
            customers.append({
                'id': sr_id,
                'name': row.get(name_col) if name_col and not pd.isna(row.get(name_col)) else f"Customer {idx+1}",
                'lat': lat,
                'lng': lng,
            })
    except Exception as e:
        print(f"Error on row {idx}: {e}")

print(f"Parsed {len(customers)} customers")
