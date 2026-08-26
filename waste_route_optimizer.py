import os
import re
import sqlite3
import pandas as pd
from flask import Flask, request, render_template, redirect, url_for, jsonify, send_file
from docx import Document
from aco_vrp import ACO_VRP
import requests
from functools import lru_cache
import time
import traceback

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'supersecretkey'

@app.errorhandler(Exception)
def handle_exception(e):
    # Return the traceback so we can debug the 500 error!
    return f"<h1>Internal Server Error</h1><pre>{traceback.format_exc()}</pre>", 500

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DB_PATH = 'routes.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Create customers table
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            address TEXT,
            location_url TEXT,
            lat REAL,
            lng REAL,
            status TEXT DEFAULT 'PENDING',
            truck_id INTEGER,
            stop_number INTEGER
        )
    ''')
    # Create metadata table for coordinates and configs
    c.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Run DB Init
init_db()


@lru_cache(maxsize=100)
def resolve_gmaps_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, allow_redirects=True, headers=headers, timeout=10)
        
        # 1. Try URL parameters
        pin_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', res.url)
        if pin_match:
            return float(pin_match.group(1)), float(pin_match.group(2))
        q_match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', res.url)
        if q_match:
            return float(q_match.group(1)), float(q_match.group(2))
        vp_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', res.url)
        if vp_match:
            return float(vp_match.group(1)), float(vp_match.group(2))
            
        # 2. Try HTML Meta Tags (for places like Dhvani Gandhi)
        meta_match = re.search(r'center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', res.text)
        if meta_match:
            return float(meta_match.group(1)), float(meta_match.group(2))
            
        # 3. Try Javascript Arrays (look for Ahmedabad coords roughly 22-24, 71-73)
        js_match = re.search(r'\[(2[2-4]\.\d+),([7][1-4]\.\d+)\]', res.text)
        if js_match:
            return float(js_match.group(1)), float(js_match.group(2))
            
    except Exception as e:
        print(f"Error resolving {url}: {e}")
    print(f"Failed to extract coordinates from: {url}")
    return None, None

def extract_lat_lng(coord_str):
    if pd.isna(coord_str):
        return None, None
    coord_str = str(coord_str).strip()
    match = re.search(r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', coord_str)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def read_data_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    df = None
    if ext == '.xlsx':
        df = pd.read_excel(filepath)
    elif ext == '.docx':
        doc = Document(filepath)
        if len(doc.tables) > 0:
            table = doc.tables[0]
            data = [[cell.text for cell in row.cells] for row in table.rows]
            df = pd.DataFrame(data[1:], columns=data[0])
        else:
            return []
    else:
        return []

    if df.empty:
        return []

    # Rename columns to standard
    cols = [str(c).lower() for c in df.columns]
    df.columns = cols
    
    customers = []
    
    coord_col = None
    lat_col = None
    lng_col = None
    
    for col in cols:
        if 'coord' in col or ('lat' in col and 'lon' in col) or ('lat' in col and 'lng' in col):
            coord_col = col
            break
            
    if not coord_col:
        lat_col = next((c for c in cols if 'lat' in c), None)
        lng_col = next((c for c in cols if 'lng' in c or 'lon' in c), None)

    name_col = next((c for c in cols if 'name' in c), cols[0])
    phone_col = next((c for c in cols if 'phone' in c), cols[1] if len(cols)>1 else None)
    address_col = next((c for c in cols if 'address' in c), cols[2] if len(cols)>2 else None)
    
    # Capture the "Location" column for Google Maps URLs
    loc_url_col = next((c for c in cols if 'location' in c and c != coord_col), None)

    # First, collect all URLs that need resolving
    urls_to_resolve = set()
    for idx, row in df.iterrows():
        loc_url_raw = row[loc_url_col] if loc_url_col and not pd.isna(row[loc_url_col]) else ""
        if loc_url_raw:
            url_match = re.search(r'(https?://[^\s]+)', str(loc_url_raw))
            if url_match:
                urls_to_resolve.add(url_match.group(1))
                
    # Resolve all URLs concurrently to prevent the UI from hanging for a minute!
    resolved_urls = {}
    import concurrent.futures
    if urls_to_resolve:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {executor.submit(resolve_gmaps_url, url): url for url in urls_to_resolve}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    resolved_urls[url] = future.result()
                except Exception:
                    resolved_urls[url] = (None, None)

    for idx, row in df.iterrows():
        lat, lng = None, None
        
        loc_url_raw = row[loc_url_col] if loc_url_col and not pd.isna(row[loc_url_col]) else ""
        loc_url_clean = ""
        if loc_url_raw:
            url_match = re.search(r'(https?://[^\s]+)', str(loc_url_raw))
            if url_match:
                loc_url_clean = url_match.group(1)
                
        # First priority: Resolve exact pin from the concurrent results
        if loc_url_clean and loc_url_clean in resolved_urls:
            url_lat, url_lng = resolved_urls[loc_url_clean]
            if url_lat and url_lng:
                lat, lng = url_lat, url_lng
                
        # Second priority: Try extracting from the legacy coordinates column (if they didn't delete it)
        if lat is None or lng is None:
            if coord_col:
                lat, lng = extract_lat_lng(row[coord_col])
            elif lat_col and lng_col:
                lat = row[lat_col]
                lng = row[lng_col]
                
        # Third priority: If everything else fails (no column, bad URL), Geocode the Address string!
        if lat is None or lng is None:
            address = row[address_col] if address_col and not pd.isna(row[address_col]) else ""
            if address:
                from geopy.geocoders import ArcGIS
                try:
                    geolocator = ArcGIS()
                    location = geolocator.geocode(address)
                    if location:
                        lat, lng = location.latitude, location.longitude
                        print(f"ArcGIS successfully geocoded: {address}")
                except Exception as e:
                    print(f"ArcGIS Geocoding failed for {address}: {e}")
            
        try:
            lat = float(lat)
            lng = float(lng)
        except (ValueError, TypeError):
            lat, lng = None, None

        if lat is not None and lng is not None and not pd.isna(lat) and not pd.isna(lng):
            customers.append({
                'id': idx + 1,
                'name': row[name_col] if name_col and not pd.isna(row[name_col]) else f"Customer {idx+1}",
                'phone': row[phone_col] if phone_col and not pd.isna(row[phone_col]) else "",
                'address': row[address_col] if address_col and not pd.isna(row[address_col]) else "",
                'location_url': loc_url_clean,
                'lat': lat,
                'lng': lng,
                'status': 'PENDING'
            })
            
    return customers

@app.route('/')
def index():
    return render_template('select_start_point.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400
        
    start_lat = request.form.get('start_lat')
    start_lng = request.form.get('start_lng')
    end_lat = request.form.get('end_lat')
    end_lng = request.form.get('end_lng')
    num_trucks = int(request.form.get('num_trucks', 3))
    
    if not all([start_lat, start_lng, end_lat, end_lng]):
        return "Missing coordinates", 400
        
    start_coord = (float(start_lat), float(start_lng))
    end_coord = (float(end_lat), float(end_lng))
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)
    
    customers = read_data_file(filepath)
    if not customers:
        return "No valid customer data found", 400
        
    aco = ACO_VRP(start_coord, end_coord, customers, num_trucks=num_trucks)
    routes, best_dist = aco.run()
    
    # Assign truck and stop numbers to customers
    for truck_idx, route in enumerate(routes):
        for stop_num, customer_id in enumerate(route):
            for c in customers:
                if c['id'] == customer_id:
                    c['truck'] = truck_idx + 1
                    c['stop_number'] = stop_num + 1

    # OVERWRITE DATABASE
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM customers')
    c.execute('DELETE FROM metadata')
    
    # Save Metadata
    c.execute('INSERT INTO metadata (key, value) VALUES (?, ?)', ('start_coord', f"{start_coord[0]},{start_coord[1]}"))
    c.execute('INSERT INTO metadata (key, value) VALUES (?, ?)', ('end_coord', f"{end_coord[0]},{end_coord[1]}"))
    
    # Save Customers
    for cust in customers:
        c.execute('''
            INSERT INTO customers (id, name, phone, address, location_url, lat, lng, status, truck_id, stop_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cust['id'], cust['name'], cust['phone'], cust['address'], cust['location_url'], 
              cust['lat'], cust['lng'], cust.get('status', 'PENDING'), cust.get('truck'), cust.get('stop_number')))
              
    conn.commit()
    conn.close()

    # Generate Excel export (optional, since DB holds it now, but good for record)
    timestamp = int(time.time())
    df = pd.DataFrame(customers)
    cols = ['truck', 'stop_number', 'name', 'phone', 'address', 'location_url', 'lat', 'lng', 'status']
    df = df[cols].sort_values(by=['truck', 'stop_number'])
    export_path = f'optimized_routes_{timestamp}.xlsx'
    df.to_excel(export_path, index=False)

    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    return render_template('live_dashboard.html')

@app.route('/api/data')
def get_data():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get Metadata
    c.execute('SELECT key, value FROM metadata')
    meta_rows = c.fetchall()
    metadata = {row['key']: row['value'] for row in meta_rows}
    
    start_coord = None
    end_coord = None
    if 'start_coord' in metadata:
        start_coord = [float(x) for x in metadata['start_coord'].split(',')]
    if 'end_coord' in metadata:
        end_coord = [float(x) for x in metadata['end_coord'].split(',')]
        
    # Get Customers
    c.execute('SELECT * FROM customers ORDER BY truck_id ASC, stop_number ASC')
    cust_rows = c.fetchall()
    
    customers = []
    routes_dict = {}
    
    for r in cust_rows:
        customers.append({
            'id': r['id'],
            'name': r['name'],
            'phone': r['phone'],
            'address': r['address'],
            'location_url': r['location_url'],
            'lat': r['lat'],
            'lng': r['lng'],
            'status': r['status'],
            'truck': r['truck_id'],
            'stop_number': r['stop_number']
        })
        t_id = r['truck_id']
        if t_id not in routes_dict:
            routes_dict[t_id] = []
        routes_dict[t_id].append(r['id'])
        
    conn.close()
    
    # Reconstruct routes array (list of lists of customer IDs)
    # E.g. if trucks are 1, 2, 3 -> routes will be [routes_dict[1], routes_dict[2], routes_dict[3]]
    routes = []
    for t_id in sorted(routes_dict.keys()):
        routes.append(routes_dict[t_id])

    return jsonify({
        'customers': customers,
        'routes': routes,
        'start_coord': start_coord,
        'end_coord': end_coord
    })

@app.route('/api/mark_completed/<int:customer_id>', methods=['POST'])
def mark_completed(customer_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE customers SET status = ? WHERE id = ?', ('COMPLETED', customer_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'status': 'COMPLETED'})

@app.route('/download_excel')
def download_excel():
    conn = get_db_connection()
    df = pd.read_sql_query('SELECT * FROM customers ORDER BY truck_id ASC, stop_number ASC', conn)
    conn.close()
    
    if df.empty:
        return "No data", 400
        
    # rename columns to match old format
    df.rename(columns={'truck_id': 'truck'}, inplace=True)
    cols = ['truck', 'stop_number', 'name', 'phone', 'address', 'location_url', 'lat', 'lng', 'status']
    df = df[cols]
    
    export_path = os.path.join(app.config['UPLOAD_FOLDER'], 'optimized_routes.xlsx')
    df.to_excel(export_path, index=False)
    
    return send_file(export_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
