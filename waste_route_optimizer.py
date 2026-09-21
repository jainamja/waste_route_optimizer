import os
import re
import pandas as pd
from werkzeug.utils import secure_filename
from flask import Flask, request, render_template, redirect, url_for, jsonify, send_file, flash
from docx import Document
from aco_vrp import ACO_VRP
import requests
from functools import lru_cache
import time
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'supersecretkey'

# Automatically use PostgreSQL if DATABASE_URL is set, otherwise fall back to local SQLite
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///routes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Models
class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    location_url = db.Column(db.Text)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    status = db.Column(db.String(50), default='PENDING')
    truck_id = db.Column(db.Integer)
    stop_number = db.Column(db.Integer)

class Metadata(db.Model):
    __tablename__ = 'metadata_store'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)

with app.app_context():
    db.create_all()
    # Auto-create a default admin user





@lru_cache(maxsize=100)
def resolve_gmaps_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, allow_redirects=True, headers=headers, timeout=10)
        
        lat, lng = None, None
        pin_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', res.url)
        if pin_match: lat, lng = float(pin_match.group(1)), float(pin_match.group(2))
        
        if not lat or not lng:
            q_match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', res.url)
            if q_match: lat, lng = float(q_match.group(1)), float(q_match.group(2))
            
        if not lat or not lng:
            vp_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', res.url)
            if vp_match: lat, lng = float(vp_match.group(1)), float(vp_match.group(2))
            
        if not lat or not lng:
            meta_match = re.search(r'center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', res.text)
            if meta_match: lat, lng = float(meta_match.group(1)), float(meta_match.group(2))
            
        if not lat or not lng:
            js_match = re.search(r'\[(2[2-4]\.\d+),([7][1-4]\.\d+)\]', res.text)
            if js_match: lat, lng = float(js_match.group(1)), float(js_match.group(2))
            
        # Validate coordinates are within India (Lat 8 to 38, Lng 68 to 98)
        if lat and lng and (8 <= lat <= 38) and (68 <= lng <= 98):
            return lat, lng
            
    except Exception as e:
        print(f"Error resolving {url}: {e}")
    return None, None

def extract_lat_lng(coord_str):
    if pd.isna(coord_str): return None, None
    match = re.search(r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', str(coord_str).strip())
    return (float(match.group(1)), float(match.group(2))) if match else (None, None)

def read_data_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    df = None
    if ext == '.csv':
        df = pd.read_csv(filepath)
    elif ext == '.xlsx':
        df = pd.read_excel(filepath)
    elif ext == '.docx':
        doc = Document(filepath)
        if doc.tables:
            table = doc.tables[0]
            data = [[cell.text for cell in row.cells] for row in table.rows]
            df = pd.DataFrame(data[1:], columns=data[0])
    
    if df is None or df.empty: return []

    cols = [str(c).lower() for c in df.columns]
    df.columns = cols
    
    coord_col = next((c for c in cols if 'coord' in c or ('lat' in c and 'lon' in c) or ('lat' in c and 'lng' in c)), None)
    lat_col = next((c for c in cols if 'lat' in c), None) if not coord_col else None
    lng_col = next((c for c in cols if 'lng' in c or 'lon' in c), None) if not coord_col else None

    name_col = next((c for c in cols if 'name' in c), cols[0])
    phone_col = next((c for c in cols if 'phone' in c), cols[1] if len(cols)>1 else None)
    address_col = next((c for c in cols if 'address' in c), cols[2] if len(cols)>2 else None)
    loc_url_col = next((c for c in cols if 'location' in c and c != coord_col), None)

    urls_to_resolve = set()
    for _, row in df.iterrows():
        loc_url_raw = row.get(loc_url_col) if loc_url_col and not pd.isna(row.get(loc_url_col)) else ""
        if loc_url_raw:
            url_match = re.search(r'(https?://[^\s]+)', str(loc_url_raw))
            if url_match: urls_to_resolve.add(url_match.group(1))
                
    resolved_urls = {}
    if urls_to_resolve:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {executor.submit(resolve_gmaps_url, url): url for url in urls_to_resolve}
            for future in concurrent.futures.as_completed(future_to_url):
                resolved_urls[future_to_url[future]] = future.result() if future.result() else (None, None)

    customers = []
    for idx, row in df.iterrows():
        lat, lng = None, None
        loc_url_clean = ""
        loc_url_raw = row.get(loc_url_col) if loc_url_col and not pd.isna(row.get(loc_url_col)) else ""
        if loc_url_raw:
            url_match = re.search(r'(https?://[^\s]+)', str(loc_url_raw))
            if url_match:
                loc_url_clean = url_match.group(1)
                if loc_url_clean in resolved_urls and resolved_urls[loc_url_clean][0]:
                    lat, lng = resolved_urls[loc_url_clean]
                
        if lat is None or lng is None:
            if coord_col: lat, lng = extract_lat_lng(row[coord_col])
            elif lat_col and lng_col: lat, lng = row[lat_col], row[lng_col]
                
        if lat is None or lng is None:
            address = row.get(address_col) if address_col and not pd.isna(row.get(address_col)) else ""
            if address:
                search_query = str(address)
                if "ahmedabad" not in search_query.lower() and "gujarat" not in search_query.lower():
                    search_query += ", Ahmedabad, Gujarat, India"
                try:
                    from geopy.geocoders import ArcGIS
                    location = ArcGIS().geocode(search_query)
                    if location: lat, lng = location.latitude, location.longitude
                except: pass
            
        try:
            lat, lng = float(lat), float(lng)
            if not pd.isna(lat) and not pd.isna(lng):
                customers.append({
                    'id': idx + 1,
                    'name': row.get(name_col) if name_col and not pd.isna(row.get(name_col)) else f"Customer {idx+1}",
                    'phone': row.get(phone_col) if phone_col and not pd.isna(row.get(phone_col)) else "",
                    'address': row.get(address_col) if address_col and not pd.isna(row.get(address_col)) else "",
                    'location_url': loc_url_clean,
                    'lat': lat,
                    'lng': lng,
                    'status': 'PENDING'
                })
        except (ValueError, TypeError):
            pass
            
    return customers

@app.route('/')
def index():
    return render_template('select_start_point.html')


@app.route('/live')
def live_tracking():
    return render_template('live_tracking.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return "No file part", 400
    file = request.files['file']
    if file.filename == '': return "No selected file", 400
        
    start_coords_json = request.form.get('start_coords_json')
    end_coords_json = request.form.get('end_coords_json')
    
    try:
        num_trucks = int(request.form.get('num_trucks') or 3)
    except ValueError:
        num_trucks = 3
    
    if not start_coords_json or not end_coords_json: return "Missing coordinates", 400
    
    import json
    starts_str = json.loads(start_coords_json)
    ends_str = json.loads(end_coords_json)
    
    start_coords = [ (float(x.split(',')[0]), float(x.split(',')[1])) for x in starts_str ]
    end_coords = [ (float(x.split(',')[0]), float(x.split(',')[1])) for x in ends_str ]
    
    filename = secure_filename(file.filename)
    if not filename:
        ext = os.path.splitext(file.filename)[1]
        filename = f"upload_fallback{ext}"
        
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    customers_data = read_data_file(filepath)
    if not customers_data: return "No valid customer data found", 400
        
    aco = ACO_VRP(start_coords, end_coords, customers_data, num_trucks=num_trucks)
    routes, route_times, route_distances = aco.run()
    
    # Filter out empty routes so truck numbering is always sequential (e.g. 1, 2, 3)
    # If the AI determines a truck isn't needed, it will drop the last truck instead of the first one.
    active_routes = []
    active_route_times = []
    active_route_distances = []
    for r, t, d in zip(routes, route_times, route_distances):
        if len(r) > 0:
            active_routes.append(r)
            active_route_times.append(t)
            active_route_distances.append(d)
            
    import secrets
    driver_tokens = {}
    
    for truck_idx, route in enumerate(active_routes):
        truck_id = truck_idx + 1
        driver_tokens[str(truck_id)] = secrets.token_urlsafe(16)
        
        for stop_num, customer_id in enumerate(route):
            for c in customers_data:
                if c['id'] == customer_id:
                    c['truck'] = truck_idx + 1
                    c['stop_number'] = stop_num + 1
                    
        # Append End Location as the final stop
        if end_coords:
            end_idx = min(truck_idx, len(end_coords) - 1)
            depot_lat, depot_lng = end_coords[end_idx]
            customers_data.append({
                'id': -1000 - truck_idx,
                'name': 'End Location / Depot',
                'phone': '',
                'address': 'Return to Depot',
                'location_url': '',
                'lat': depot_lat,
                'lng': depot_lng,
                'status': 'PENDING',
                'truck': truck_idx + 1,
                'stop_number': len(route) + 1
            })

    # Validation checks
    assigned_ids = set()
    duplicate_ids = set()
    for route in active_routes:
        for cid in route:
            if cid in assigned_ids:
                duplicate_ids.add(cid)
            assigned_ids.add(cid)
    
    unassigned_customers = [c['id'] for c in customers_data if 'stop_number' not in c and c['id'] > -1000]
    if duplicate_ids:
        print(f"[WARNING] Route generation assigned duplicate stops: {duplicate_ids}")
    if unassigned_customers:
        print(f"[WARNING] Route generation failed to assign stops for: {unassigned_customers}")

    # Clear old data
    Customer.query.delete()
    Metadata.query.delete()
    
    # Insert new data
    import json
    m1 = Metadata(key='start_coords', value=json.dumps(starts_str))
    m2 = Metadata(key='end_coords', value=json.dumps(ends_str))
    m3 = Metadata(key='route_times', value=json.dumps(active_route_times))
    m4 = Metadata(key='route_distances', value=json.dumps(active_route_distances))
    m_tokens = Metadata(key='driver_tokens', value=json.dumps(driver_tokens))
    db.session.add_all([m1, m2, m3, m4, m_tokens])
    
    for c in customers_data:
        new_cust = Customer(
            id=c['id'], name=c['name'], phone=c['phone'], address=c['address'],
            location_url=c['location_url'], lat=c['lat'], lng=c['lng'],
            status=c.get('status', 'PENDING'), truck_id=c.get('truck'), stop_number=c.get('stop_number')
        )
        db.session.add(new_cust)
        
    db.session.commit()

    # INSERT TO FIREBASE
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        
                    "name": c['name'],
                    "address": c['address'],
                    "lat": c['lat'],
                    "lng": c['lng'],
                    "sequence": c.get('stop_number', None),
                    "status": "PENDING"
                }
        requests.patch(f"{firebase_url}/.json", json=updates)
    except Exception as e:
        print("Firebase sync error:", e)


    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if not Customer.query.first():
        return redirect(url_for('index'))
    return render_template('live_dashboard.html')

@app.route('/driver')
def driver_view():
    return render_template('driver_view.html')

@app.route('/api/data')
def get_data():
    metadata_rows = Metadata.query.all()
    metadata = {row.key: row.value for row in metadata_rows}
    
    import json
    
    # Fallback to single string for legacy database compatibility
    if 'start_coords' in metadata:
        start_coords = json.loads(metadata['start_coords'])
    elif 'start_coord' in metadata:
        start_coords = [metadata['start_coord']]
    else:
        start_coords = []
        
    if 'end_coords' in metadata:
        end_coords = json.loads(metadata['end_coords'])
    elif 'end_coord' in metadata:
        end_coords = [metadata['end_coord']]
    else:
        end_coords = []
        
    customers_db = Customer.query.order_by(Customer.truck_id.asc(), Customer.stop_number.asc()).all()
    
    customers = []
    routes_dict = {}
    
    for r in customers_db:
        customers.append({
            'id': r.id, 'name': r.name, 'phone': r.phone, 'address': r.address,
            'location_url': r.location_url, 'lat': r.lat, 'lng': r.lng,
            'status': r.status, 'truck': r.truck_id, 'stop_number': r.stop_number
        })
        t_id = r.truck_id
        if t_id not in routes_dict: routes_dict[t_id] = []
        routes_dict[t_id].append(r.id)
        
    routes = [routes_dict[t_id] for t_id in sorted(routes_dict.keys())]
    
    route_times = []
    if 'route_times' in metadata:
        route_times = json.loads(metadata['route_times'])
        
    route_distances = []
    if 'route_distances' in metadata:
        route_distances = json.loads(metadata['route_distances'])
        
    driver_tokens = {}
    if 'driver_tokens' in metadata:
        driver_tokens = json.loads(metadata['driver_tokens'])

    return jsonify({
        'customers': customers,
        'routes': routes,
        'route_times': route_times,
        'route_distances': route_distances,
        'start_coords': start_coords,
        'end_coords': end_coords,
        'driver_tokens': driver_tokens
    })

@app.route('/api/mark_completed/<int:customer_id>', methods=['POST'])
def mark_completed(customer_id):
    customer = db.session.get(Customer, customer_id)
    if customer:
        customer.status = 'COMPLETED'
        db.session.commit()

    # INSERT TO FIREBASE
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        
        updates = {}
        for c in customers_data:
            tid = c.get('truck')
            if tid:
                route_key = f"routes/route_{tid}/stops/{c['id']}"
                updates[route_key] = {
                    "name": c['name'],
                    "address": c['address'],
                    "lat": c['lat'],
                    "lng": c['lng'],
                    "sequence": c.get('stop_number', None),
                    "status": "PENDING"
                }
        requests.patch(f"{firebase_url}/.json", json=updates)
    except Exception as e:
        print("Firebase sync error:", e)

    return jsonify({'success': True, 'status': 'COMPLETED'})

@app.route('/api/resolve_token')
def resolve_token():
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Missing token'}), 400
        
    token_meta = Metadata.query.filter_by(key='driver_tokens').first()
    if not token_meta:
        return jsonify({'error': 'No tokens found'}), 404
        
    import json
    driver_tokens = json.loads(token_meta.value)
    
    # Reverse lookup: find truck_id that has this token
    truck_id = next((tid for tid, tok in driver_tokens.items() if tok == token), None)
    
    if truck_id:
        return jsonify({'truck_id': truck_id})
    else:
        return jsonify({'error': 'Invalid token'}), 404

@app.route('/download_excel')
def download_excel():
    customers = Customer.query.order_by(Customer.truck_id.asc(), Customer.stop_number.asc()).all()
    if not customers: return "No data", 400
    
    data = [{
        'truck': c.truck_id, 'stop_number': c.stop_number, 'name': c.name,
        'phone': c.phone, 'address': c.address, 'location_url': c.location_url,
        'lat': c.lat, 'lng': c.lng, 'status': c.status
    } for c in customers]
    
    df = pd.DataFrame(data)
    export_path = os.path.join(app.config['UPLOAD_FOLDER'], 'optimized_routes.xlsx')
    df.to_excel(export_path, index=False)
    
    return send_file(export_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)


@app.route('/api/dynamic_recalculate', methods=['POST'])
def dynamic_recalculate():
    import requests
    firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
    
    try:
        # 1. Fetch current GPS for all trucks
        trucks_res = requests.get(f"{firebase_url}/trucks.json")
        trucks_data = trucks_res.json() or {}
        
        # 2. Fetch all current routes
        routes_res = requests.get(f"{firebase_url}/routes.json")
        routes_data = routes_res.json() or {}
        
        pending_customers = []
        truck_starts = []
        active_truck_ids = []
        
        # For each truck, get its position and pending stops
        trucks_items = trucks_data.items() if isinstance(trucks_data, dict) else enumerate(trucks_data) if isinstance(trucks_data, list) else []
        for truck_id, truck_info in trucks_items:
            if not truck_info: continue
            truck_id = str(truck_id)
            if truck_info.get('status') == 'online' and truck_info.get('currentLat'):
                truck_starts.append((float(truck_info['currentLat']), float(truck_info['currentLng'])))
                active_truck_ids.append(truck_id)
                
                # Get pending stops for this truck
                route_key = f"route_{truck_id}"
                if route_key in routes_data and 'stops' in routes_data[route_key]:
                    stops_raw = routes_data[route_key]['stops']
                    stops_items = stops_raw.items() if isinstance(stops_raw, dict) else enumerate(stops_raw) if isinstance(stops_raw, list) else []
                    for stop_id, stop_info in stops_items:
                        if not stop_info: continue
                        if stop_info.get('status') == 'PENDING':
                            pending_customers.append({
                                'id': str(stop_id),
                                'name': stop_info.get('name', ''),
                                'address': stop_info.get('address', ''),
                                'lat': float(stop_info['lat']),
                                'lng': float(stop_info['lng'])
                            })
                            
        if not truck_starts:
            return jsonify({'error': 'No online trucks found. Open the driver app so it sends GPS data!'}), 400
            
        if not pending_customers:
            return jsonify({'error': 'No pending stops to recalculate.'}), 400
            
        # Filter out end depots from pending_customers so they aren't treated as mid-route stops
        real_pending_customers = [c for c in pending_customers if int(c['id']) > -1000]
        
        # 3. Fetch true end coords from DB
        import json
        end_coords_meta = Metadata.query.filter_by(key='end_coords').first()
        if end_coords_meta:
            saved_ends = json.loads(end_coords_meta.value)
            true_ends = [ (float(x.split(',')[0]), float(x.split(',')[1])) for x in saved_ends ]
            # Map end coords to trucks
            end_coords = [true_ends[min(i, len(true_ends)-1)] for i in range(len(truck_starts))]
        else:
            end_coords = [truck_starts[0]] * len(truck_starts)
        
        aco = ACO_VRP(truck_starts, end_coords, real_pending_customers, num_trucks=len(truck_starts))
        new_routes, _, _ = aco.run()
        
        # 4. Write back to Firebase
        updates = {}
        for idx, route in enumerate(new_routes):
            if idx < len(active_truck_ids):
                tid = active_truck_ids[idx]
                
                start_seq = 1
                route_key = f"route_{tid}"
                if route_key in routes_data and 'stops' in routes_data[route_key]:
                    stops_raw = routes_data[route_key]['stops']
                    stops_items = stops_raw.items() if isinstance(stops_raw, dict) else enumerate(stops_raw) if isinstance(stops_raw, list) else []
                    for s_id, s_info in stops_items:
                        if s_info and s_info.get('status') != 'PENDING' and int(s_id) > -1000:
                            start_seq += 1
                
                # We overwrite the remaining sequence for this truck
                for seq, cust_id in enumerate(route):
                    # We find the customer data
                    cust = next((c for c in real_pending_customers if c['id'] == cust_id), None)
                    if cust:
                        updates[f"routes/route_{tid}/stops/{cust_id}"] = {
                            "name": cust['name'],
                            "address": cust['address'],
                            "lat": cust['lat'],
                            "lng": cust['lng'],
                            "sequence": start_seq + seq,
                            "status": "PENDING"
                        }
                
                # Re-append End Depot at the end of this truck's route
                depot_lat, depot_lng = end_coords[idx]
                updates[f"routes/route_{tid}/stops/{-1000 - idx}"] = {
                    "name": "End Location / Depot",
                    "address": "Return to Depot",
                    "lat": depot_lat,
                    "lng": depot_lng,
                    "sequence": start_seq + len(route),
                    "status": "PENDING"
                }
                        
        # Because we re-balanced globally, we need to clear ALL pending stops first 
        # so they don't linger on old trucks if reassigned.
        for tid in active_truck_ids:
            route_key = f"route_{tid}"
            if route_key in routes_data and 'stops' in routes_data[route_key]:
                stops_raw = routes_data[route_key]['stops']
                stops_items = stops_raw.items() if isinstance(stops_raw, dict) else enumerate(stops_raw) if isinstance(stops_raw, list) else []
                for stop_id, stop_info in stops_items:
                    if not stop_info: continue
                    if stop_info.get('status') == 'PENDING':
                        requests.delete(f"{firebase_url}/routes/{route_key}/stops/{stop_id}.json")
                        
        # Now PATCH the new assignments
        requests.patch(f"{firebase_url}/.json", json=updates)
        
        return jsonify({'success': True, 'recalculated_stops': len(pending_customers)})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

