import os
import re
import pandas as pd
from werkzeug.utils import secure_filename
from flask import Flask, request, render_template, redirect, url_for, jsonify, send_file, flash, make_response, send_from_directory
from werkzeug.exceptions import HTTPException
from docx import Document
from aco_vrp import ACO_VRP
import requests
from functools import lru_cache
import time
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS


_firebase_token_cache = {"token": None, "expires": 0}
def get_firebase_token():
    import time, requests
    global _firebase_token_cache
    if _firebase_token_cache["token"] and time.time() < _firebase_token_cache["expires"]:
        return _firebase_token_cache["token"]
        
    API_KEY = "AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg"
    auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
    auth_res = requests.post(auth_url, json={"returnSecureToken": True})
    if auth_res.status_code == 200:
        _firebase_token_cache["token"] = auth_res.json().get('idToken')
        _firebase_token_cache["expires"] = time.time() + 3000 # 50 minutes
        return _firebase_token_cache["token"]
    return None

app = Flask(__name__)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'logo.jpg', mimetype='image/jpeg')

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    import traceback
    return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'supersecretkey'

# Automatically use PostgreSQL if DATABASE_URL is set, otherwise fall back to local SQLite
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    elif database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///routes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


app.secret_key = 'super_secret_waste_route_key_123'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(20))
    truck_id = db.Column(db.Integer)
    name = db.Column(db.String(100))
    assigned_template_id = db.Column(db.Integer, nullable=True)

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    location_url = db.Column(db.Text)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    status = db.Column(db.String(50), default='PENDING')
    truck_id = db.Column(db.Integer)
    stop_number = db.Column(db.Integer)
    confirmation = db.Column(db.String(20), default='NOT_CONFIRMED')
    customer_status = db.Column(db.String(20), default='ACTIVE')

class Metadata(db.Model):
    __tablename__ = 'metadata_store'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)


class SavedTemplate(db.Model):
    __tablename__ = 'saved_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    metadata_json = db.Column(db.Text)
    customers_json = db.Column(db.Text)
    is_assigned_instance = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()
    
    from sqlalchemy import text
    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN truck_id INTEGER;'))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN name VARCHAR(100);'))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN assigned_template_id INTEGER;'))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN confirmation VARCHAR(20) DEFAULT 'NOT_CONFIRMED';"))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN customer_status VARCHAR(20) DEFAULT 'ACTIVE';"))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE customers ALTER COLUMN id TYPE BIGINT;"))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE saved_templates ADD COLUMN is_assigned_instance BOOLEAN DEFAULT FALSE;"))
        db.session.commit()
    except:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE saved_templates ADD COLUMN is_assigned_instance BOOLEAN DEFAULT 0;"))
            db.session.commit()
        except:
            db.session.rollback()

    try:
        db.session.execute(text("UPDATE saved_templates SET is_assigned_instance = FALSE WHERE is_assigned_instance IS NULL;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        drivers_with_tmpl = User.query.filter(User.assigned_template_id != None).all()
        for d in drivers_with_tmpl:
            orig_t = db.session.get(SavedTemplate, d.assigned_template_id)
            if orig_t and not getattr(orig_t, 'is_assigned_instance', False):
                inst = SavedTemplate(
                    name=orig_t.name,
                    metadata_json=orig_t.metadata_json,
                    customers_json=orig_t.customers_json,
                    is_assigned_instance=True
                )
                db.session.add(inst)
                db.session.flush()
                d.assigned_template_id = inst.id
        db.session.commit()
    except:
        db.session.rollback()
        
    from werkzeug.security import generate_password_hash
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        db.session.add(User(username='admin', password_hash=generate_password_hash('admin'), role='ADMIN'))
        for i in range(1, 11):
            db.session.add(User(username='driver'+str(i), password_hash=generate_password_hash('driver'+str(i)), role='DRIVER', truck_id=i))
        db.session.commit()
    else:
        from werkzeug.security import check_password_hash
        if not check_password_hash(admin_user.password_hash, 'admin'):
            admin_user.password_hash = generate_password_hash('admin')
            db.session.commit()

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
            
            
        # Validate coordinates are within India (Lat 8 to 38, Lng 68 to 98)
        if lat and lng and (8 <= lat <= 38) and (68 <= lng <= 98):
            return lat, lng
            
        import urllib.parse
        unquoted_url = urllib.parse.unquote_plus(res.url)
        place_match = re.search(r'place/([^/]+)/', unquoted_url)
        if place_match:
            place_name = place_match.group(1).replace('+', ' ').strip()
            return None, place_name
            
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

    # Auto-detect missing headers (if a column name is a URL or a pure integer)
    has_no_header = any('http' in str(c) or 'maps.app' in str(c) for c in df.columns)
    if has_no_header:
        new_row = pd.DataFrame([df.columns], columns=df.columns)
        df = pd.concat([new_row, df], ignore_index=True)
        df.columns = [str(i) for i in range(len(df.columns))]

    cols = [str(c).lower() for c in df.columns]
    df.columns = cols
    
    coord_col = next((c for c in cols if 'coord' in c or ('lat' in c and 'lon' in c) or ('lat' in c and 'lng' in c)), None)
    lat_col = next((c for c in cols if 'lat' in c), None) if not coord_col else None
    lng_col = next((c for c in cols if 'lng' in c or 'lon' in c), None) if not coord_col else None

    # Smart detect URL
    loc_url_col = next((c for c in cols if 'location' in c and c != coord_col), None)
    if not loc_url_col:
        for c in cols:
            first_val = str(df[c].dropna().head(1).iloc[0]) if len(df[c].dropna()) else ""
            if 'http' in first_val or 'maps.app' in first_val:
                loc_url_col = c
                break


    def is_sr_col(c):
        c_low = str(c).lower().strip()
        if any(p in c_low for p in ['phone', 'mobile', 'contact', 'tel', 'cell', 'whatsapp', 'ward', 'flat', 'house', 'plot', 'door', 'pincode', 'pin', 'zip']):
            return False
        if c_low in ['id', 'no', 'no.', '#', 's_no', 's.no', 'sr_no', 'sr.no', 'sr. no.', 'sr no', 'sr. no', 'serial']:
            return True
        if c_low.startswith('sr') or 'serial' in c_low or 's.no' in c_low or 'sr_no' in c_low:
            return True
        return False

    sr_no_col = next((c for c in cols if is_sr_col(c)), None)
    
    name_col = next((c for c in cols if 'name' in c), None)
    if not name_col:
        for c in cols:
            if c != loc_url_col and c != coord_col:
                first_val = str(df[c].dropna().head(1).iloc[0]) if len(df[c].dropna()) else ""
                if not first_val.isdigit() and len(first_val) > 2 and len(first_val) < 50:
                    name_col = c
                    break
        if not name_col: name_col = cols[0]

    address_col = next((c for c in cols if 'address' in c), None)
    if not address_col:
        max_len = 0
        for c in cols:
            if c not in [loc_url_col, name_col, coord_col]:
                avg_len = df[c].astype(str).str.len().mean()
                if avg_len > max_len:
                    max_len = avg_len
                    address_col = c

    phone_col = next((c for c in cols if any(p in c for p in ['phone', 'mobile', 'contact', 'cell', 'tel', 'whatsapp'])), None)
    if not phone_col:
        for c in cols:
            if c not in [loc_url_col, name_col, coord_col, address_col, sr_no_col]:
                first_val = str(df[c].dropna().head(1).iloc[0]) if len(df[c].dropna()) else ""
                clean_val = ''.join(filter(str.isdigit, first_val))
                if len(clean_val) >= 9 and len(clean_val) <= 15:
                    phone_col = c
                    break
                    
    urls_to_resolve = set()
    for _, row in df.iterrows():
          # Fix shifted URLs
          loc_url_raw = row.get(loc_url_col) if loc_url_col and not pd.isna(row.get(loc_url_col)) else ""
          if not loc_url_raw or 'http' not in str(loc_url_raw):
              for val in row:
                  if pd.notna(val) and isinstance(val, str) and 'http' in val:
                      loc_url_raw = val
                      break
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
    seen_ids = set()
    for idx, row in df.iterrows():
        lat, lng = None, None
        loc_url_clean = ""
        
        # Fix shifted URLs
        loc_url_raw = row.get(loc_url_col) if loc_url_col and not pd.isna(row.get(loc_url_col)) else ""
        if not loc_url_raw or 'http' not in str(loc_url_raw):
            for val in row:
                if pd.notna(val) and isinstance(val, str) and 'http' in val:
                    loc_url_raw = val
                    break
        
        if loc_url_raw:
            url_match = re.search(r'(https?://[^\s]+)', str(loc_url_raw))
            if url_match:
                loc_url_clean = url_match.group(1)
                if loc_url_clean in resolved_urls:
                    res_tuple = resolved_urls[loc_url_clean]
                    if res_tuple[0] is not None or res_tuple[1] is not None:
                        lat, lng = res_tuple
                
        if lat is None or lng is None:
            if coord_col: lat, lng = extract_lat_lng(row[coord_col])
            elif lat_col and lng_col: lat, lng = row[lat_col], row[lng_col]
                
        if lat is None or lng is None:
            address = str(row.get(address_col)) if address_col and not pd.isna(row.get(address_col)) else ""
            
            # Fix shifted Address
            if 'http' in address:
                max_l = 0
                address = ''
                for val in row:
                    if pd.notna(val) and isinstance(val, str) and 'http' not in val and len(val) > max_l:
                        max_l = len(val)
                        address = val
                        
            if lat is None and isinstance(lng, str):
                if not address or len(address) < 5:
                    address = lng
                lng = None

            if address:
                search_query = str(address)
                if "ahmedabad" not in search_query.lower() and "gujarat" not in search_query.lower():
                    search_query += ", Ahmedabad, Gujarat, India"
                gmaps_key = os.environ.get('GMAPS_API_KEY')
                if gmaps_key:
                    try:
                        import requests
                        g_res = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params={'address': search_query, 'key': gmaps_key}).json()
                        if g_res.get('status') == 'OK':
                            lat = g_res['results'][0]['geometry']['location']['lat']
                            lng = g_res['results'][0]['geometry']['location']['lng']
                    except Exception as e: print(f"GMAPS Geocode Error: {e}")
                if lat is None or lng is None:
                    try:
                        from geopy.geocoders import Nominatim
                        nom = Nominatim(user_agent="waste_route_123")
                        parts = [p.strip() for p in search_query.split(',')]
                        queries = [search_query]
                        if len(parts) >= 5: queries.append(", ".join(parts[-5:]))
                        if len(parts) >= 4: queries.append(", ".join(parts[-4:]))
                        if len(parts) >= 3: queries.append(", ".join(parts[-3:]))
                        if len(parts) >= 2: queries.append(", ".join(parts[-2:]))
                          
                        # Progressive Nominatim (strict but accurate)
                        for short_q in queries:
                            try:
                                print(f'NOM TRY: {short_q}')
                                loc = nom.geocode(short_q, timeout=3)
                                if loc:
                                    lat, lng = loc.latitude, loc.longitude
                                    break
                            except: pass
                              
                        # If still none, fallback to progressive ArcGIS
                        if lat is None or lng is None:
                            from geopy.geocoders import ArcGIS
                            arc = ArcGIS()
                            for short_q in queries:
                                try:
                                    print(f'ARC TRY: {short_q}')
                                    loc = arc.geocode(short_q, timeout=3)
                                    if loc:
                                        lat, lng = loc.latitude, loc.longitude
                                        break
                                except: pass
                    except: pass
            
        try:
            try:
                sr_id = None
                if sr_no_col and not pd.isna(row[sr_no_col]):
                    val_str = str(row[sr_no_col]).strip()
                    if val_str.endswith('.0'):
                        val_str = val_str[:-2]
                    if val_str.isdigit():
                        parsed_val = int(val_str)
                        if 0 < parsed_val < 100000000 and parsed_val not in seen_ids:
                            sr_id = parsed_val
                if sr_id is None:
                    sr_id = max(seen_ids, default=0) + 1
            except:
                sr_id = max(seen_ids, default=0) + 1

            seen_ids.add(sr_id)

            phone_val = ""
            if phone_col and not pd.isna(row.get(phone_col)):
                raw_phone = str(row.get(phone_col)).strip()
                if raw_phone.endswith('.0'):
                    raw_phone = raw_phone[:-2]
                phone_val = raw_phone

            lat, lng = float(lat), float(lng)
            if not pd.isna(lat) and not pd.isna(lng):
                customers.append({
                    'id': sr_id,
                    'name': row.get(name_col) if name_col and not pd.isna(row.get(name_col)) else f"Customer {idx+1}",
                    'phone': phone_val,
                    'address': row.get(address_col) if address_col and not pd.isna(row.get(address_col)) else "",
                    'location_url': loc_url_clean,
                    'lat': lat,
                    'lng': lng,
                    'status': 'PENDING',
                    'customer_status': 'ACTIVE'
                })
        except (ValueError, TypeError):
            pass
            
    return customers

from functools import wraps
from flask import session, redirect, url_for, request

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

leg_cache = {}

def get_active_assigned_trucks(exclude_template_id=None):
    q = User.query.filter(User.role == 'DRIVER', User.assigned_template_id != None, User.truck_id != None)
    if exclude_template_id is not None:
        try:
            q = q.filter(User.assigned_template_id != int(exclude_template_id))
        except:
            pass
    active_trucks = set()
    for d in q.all():
        pending_cnt = Customer.query.filter(
            Customer.truck_id == d.truck_id,
            Customer.id > -1000,
            Customer.status == 'PENDING'
        ).count()
        if pending_cnt > 0:
            active_trucks.add(int(d.truck_id))
    return active_trucks

def recompute_route_metrics():
    import json
    from geopy.distance import geodesic
    try:
        start_meta = Metadata.query.filter_by(key='start_coords').first()
        if not start_meta or not start_meta.value:
            return
            
        start_coords = json.loads(start_meta.value)
        
        ws_meta = Metadata.query.filter_by(key='workspace_truck_ids').first()
        ws_trucks = None
        if ws_meta and ws_meta.value:
            try:
                ws_trucks = json.loads(ws_meta.value)
            except:
                ws_trucks = None
                
        q = Customer.query.filter(Customer.truck_id != None)
        if ws_trucks:
            q = q.filter(Customer.truck_id.in_(ws_trucks))
        customers = q.order_by(Customer.truck_id, Customer.stop_number).all()
        truck_map = {}
        for c in customers:
            if c.truck_id not in truck_map:
                truck_map[c.truck_id] = []
            truck_map[c.truck_id].append(c)
            
        if not truck_map:
            return
            
        sorted_trucks = sorted(truck_map.keys())
        route_times = []
        route_distances = []
        
        gmaps_key = os.environ.get('GMAPS_API_KEY')
        
        for idx, truck_id in enumerate(sorted_trucks):
            stops = truck_map[truck_id]
            if not stops:
                route_times.append(0)
                route_distances.append(0)
                continue
                
            depots = [s for s in stops if s.id <= -1000 or s.name == 'End Location / Depot']
            real_stops = [s for s in stops if s.id > -1000 and s.name != 'End Location / Depot' and s.confirmation != 'CANCELLED']
            depot_stop = depots[-1] if depots else None
            
            start_idx = min(idx, len(start_coords) - 1)
            slat, slng = map(float, start_coords[start_idx].split(','))
            
            waypoints = [(slat, slng)]
            for s in real_stops:
                waypoints.append((s.lat, s.lng))
            if depot_stop:
                waypoints.append((depot_stop.lat, depot_stop.lng))
                
            if len(real_stops) == 0:
                route_times.append(0)
                route_distances.append(0)
                continue
                
            truck_dist = 0
            truck_time = 300 * len(real_stops) # 300s per real stop
            
            chunk_size = 90
            for i in range(0, len(waypoints) - 1, chunk_size - 1):
                chunk = waypoints[i:i + chunk_size]
                if len(chunk) < 2:
                    break
                    
                success = False
                if gmaps_key:
                    try:
                        for j in range(len(chunk) - 1):
                            c1 = chunk[j]
                            c2 = chunk[j+1]
                            rounded1 = (round(c1[0], 5), round(c1[1], 5))
                            rounded2 = (round(c2[0], 5), round(c2[1], 5))
                            key = (rounded1, rounded2)
                            if key in leg_cache:
                                t, d = leg_cache[key]
                                truck_dist += d
                                truck_time += t
                            else:
                                url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={c1[0]},{c1[1]}&destinations={c2[0]},{c2[1]}&key={gmaps_key}"
                                resp = requests.get(url, timeout=8).json()
                                row = resp.get('rows', [{}])[0].get('elements', [{}])[0]
                                if row.get('status') == 'OK':
                                    d = row['distance']['value']
                                    t = row['duration']['value']
                                    leg_cache[key] = (t, d)
                                    truck_dist += d
                                    truck_time += t
                                else:
                                    raise Exception("GMAPS fail")
                        success = True
                    except Exception as e:
                        print(f"GMAPS Error in recompute: {e}")
                
                if not success and not gmaps_key:
                    coords_str = ";".join([f"{lon},{lat}" for lat, lon in chunk])
                    osrm_url = f"https://router.project-osrm.org/route/v1/driving/{coords_str}?overview=false"
                    try:
                        resp = requests.get(osrm_url, timeout=8)
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get('code') == 'Ok' and data.get('routes'):
                                legs = data['routes'][0].get('legs', [])
                                if len(legs) == len(chunk) - 1:
                                    for leg in legs:
                                        truck_dist += leg['distance']
                                        truck_time += leg['duration']
                                    success = True
                    except Exception as e:
                        print(f"OSRM Error in recompute: {e}")
                
                if not success:
                    for j in range(len(chunk) - 1):
                        c1 = chunk[j]
                        c2 = chunk[j+1]
                        rounded1 = (round(c1[0], 5), round(c1[1], 5))
                        rounded2 = (round(c2[0], 5), round(c2[1], 5))
                        key = (rounded1, rounded2)
                        if key not in leg_cache:
                            dist_m = geodesic(c1, c2).meters
                            time_s = dist_m / 10.0
                            leg_cache[key] = (time_s, dist_m)
                        t, d = leg_cache[key]
                        truck_dist += d
                        truck_time += t

            route_times.append(int(truck_time))
            route_distances.append(int(truck_dist))
            
        meta_times = Metadata.query.filter_by(key='route_times').first()
        if not meta_times:
            meta_times = Metadata(key='route_times')
            db.session.add(meta_times)
        meta_times.value = json.dumps(route_times)
        
        meta_dists = Metadata.query.filter_by(key='route_distances').first()
        if not meta_dists:
            meta_dists = Metadata(key='route_distances')
            db.session.add(meta_dists)
        meta_dists.value = json.dumps(route_distances)
        
        db.session.commit()
    except Exception as e:
        print(f"Error recomputing route metrics: {e}")

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        from werkzeug.security import check_password_hash
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/generate')
@login_required
def index():
    return render_template('select_start_point.html')

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('admin_dashboard.html')

@app.route('/routes')
@login_required
def route_dashboard():
    return render_template('live_dashboard.html')

@app.route('/live')
@login_required
def live_tracking():
    resp = make_response(render_template('live_tracking.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/drivers', methods=['GET'])
@login_required
def get_drivers():
    drivers = User.query.filter_by(role='DRIVER').all()
    drivers_data = []
    for d in drivers:
        assigned_name = "No Route Assigned"
        if getattr(d, 'assigned_template_id', None):
            t = db.session.get(SavedTemplate, d.assigned_template_id)
            if t: assigned_name = t.name
            
        drivers_data.append({
            'id': d.id,
            'username': d.username,
            'name': d.name,
            'truck_id': d.truck_id,
            'password_hash': 'redacted',
            'assigned_template_id': getattr(d, 'assigned_template_id', None),
            'assigned_template_name': assigned_name
        })
    return jsonify({'drivers': drivers_data})

@app.route('/upload', methods=['POST'])
@login_required
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
    protected_trucks = get_active_assigned_trucks()
    used_trucks = set(protected_trucks)
    workspace_trucks = []
    
    for truck_idx, route in enumerate(active_routes):
        truck_id = truck_idx + 1
        while truck_id in used_trucks:
            truck_id += 1
        used_trucks.add(truck_id)
        workspace_trucks.append(truck_id)
        driver_tokens[str(truck_id)] = secrets.token_urlsafe(16)
        
        for stop_num, customer_id in enumerate(route):
            for c in customers_data:
                if c['id'] == customer_id:
                    c['truck'] = truck_id
                    c['stop_number'] = stop_num + 1
                    
        # Append End Location as the final stop
        if end_coords:
            end_idx = min(truck_idx, len(end_coords) - 1)
            depot_lat, depot_lng = end_coords[end_idx]
            customers_data.append({
                'id': -1000 - truck_id,
                'name': 'End Location / Depot',
                'phone': '',
                'address': 'Return to Depot',
                'location_url': '',
                'lat': depot_lat,
                'lng': depot_lng,
                'status': 'PENDING',
                'truck': truck_id,
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

    # Clear old unassigned/non-active data while preserving active assigned trucks
    if protected_trucks:
        Customer.query.filter((Customer.truck_id == None) | (~Customer.truck_id.in_(list(protected_trucks)))).delete(synchronize_session=False)
    else:
        Customer.query.delete()
    Metadata.query.delete()
    
    # Insert new data
    import json
    m1 = Metadata(key='start_coords', value=json.dumps(starts_str))
    m2 = Metadata(key='end_coords', value=json.dumps(ends_str))
    m3 = Metadata(key='route_times', value=json.dumps(active_route_times))
    m4 = Metadata(key='route_distances', value=json.dumps(active_route_distances))
    m_tokens = Metadata(key='driver_tokens', value=json.dumps(driver_tokens))
    m_template = Metadata(key='is_from_template', value='false')
    m_ws = Metadata(key='workspace_truck_ids', value=json.dumps(workspace_trucks))
    db.session.add_all([m1, m2, m3, m4, m_tokens, m_template, m_ws])
    
    existing_ids = set(r[0] for r in db.session.query(Customer.id).all())
    max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
    if max_id < 0:
        max_id = 0

    for c in customers_data:
        cid = int(c['id'])
        if cid <= -1000 or c.get('name') == 'End Location / Depot':
            cid = -1000 - int(c.get('truck') or 1)
            if cid in existing_ids:
                Customer.query.filter_by(id=cid).delete()
        else:
            if cid in existing_ids:
                max_id += 1
                cid = max_id
        existing_ids.add(cid)
        c['id'] = cid
        new_cust = Customer(
            id=cid, name=c['name'], phone=c['phone'], address=c['address'],
            location_url=c['location_url'], lat=c['lat'], lng=c['lng'],
            status=c.get('status', 'PENDING'), truck_id=c.get('truck'), stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED')
        )
        db.session.add(new_cust)
        
    db.session.commit()

    # INSERT TO FIREBASE
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        
        id_token = get_firebase_token()
        if id_token:
            
            # Clear only non-protected old data in Firebase
            trucks_res = requests.get(f"{firebase_url}/trucks.json?auth={id_token}")
            if trucks_res.status_code == 200 and trucks_res.json():
                trucks_data = trucks_res.json()
                trucks_items = trucks_data.items() if isinstance(trucks_data, dict) else enumerate(trucks_data) if isinstance(trucks_data, list) else []
                for tid, val in trucks_items:
                    if val is not None:
                        try:
                            if int(tid) in protected_trucks:
                                continue
                        except:
                            pass
                        requests.delete(f"{firebase_url}/trucks/{tid}.json?auth={id_token}")
                    
            routes_res = requests.get(f"{firebase_url}/routes.json?auth={id_token}")
            if routes_res.status_code == 200 and routes_res.json():
                routes_data = routes_res.json()
                routes_items = routes_data.items() if isinstance(routes_data, dict) else enumerate(routes_data) if isinstance(routes_data, list) else []
                for rid, val in routes_items:
                    if val is not None:
                        try:
                            tid_num = int(str(rid).replace('route_', ''))
                            if tid_num in protected_trucks:
                                continue
                        except:
                            pass
                        requests.delete(f"{firebase_url}/routes/{rid}.json?auth={id_token}")
            
            # Group updates by route
            routes_payload = {}
            for c in customers_data:
                tid = c.get('truck')
                if tid:
                    route_key = f"route_{tid}"
                    if route_key not in routes_payload: routes_payload[route_key] = {}
                    
                    routes_payload[route_key][str(c['id'])] = {
                        "name": c['name'],
                        "address": c['address'],
                        "phone": c.get('phone', ''),
                        "lat": c['lat'],
                        "lng": c['lng'],
                        "sequence": c.get('stop_number', None),
                        "status": "PENDING",
                        "confirmation": c.get("confirmation", "NOT_CONFIRMED"),
                        "customer_status": c.get("customer_status", "ACTIVE")
                    }
                    
            for route_key, stops in routes_payload.items():
                res = requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops})
                if res.status_code != 200:
                    print(f"Failed to write {route_key}: {res.text}")
                    
                # also init the truck so it exists for tracking
                tid = route_key.split('_')[1]
                requests.put(f"{firebase_url}/trucks/{tid}.json?auth={id_token}", json={"status": "offline"})
        else:
            print("Backend Firebase Auth failed:", auth_res.text)
            
    except Exception as e:
        print("Firebase sync error:", e)


    return redirect(url_for('route_dashboard'))

@app.route('/api/driver_login', methods=['POST'])
def driver_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    from werkzeug.security import check_password_hash
    user = User.query.filter_by(username=username, role='DRIVER').first()
    
    if user and check_password_hash(user.password_hash, password):
        return jsonify({
            'success': True,
            'token': str(user.id),
            'name': user.name,
            'username': user.username,
            'truck_id': str(user.truck_id) if user.truck_id is not None else None
        })
    else:
        return jsonify({'error': 'Invalid mobile number or password'}), 401

@app.route('/api/admin_create_driver', methods=['POST'])
@login_required
def admin_create_driver():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    name = data.get('name')
    if not username or not password or not name:
        return jsonify({'error': 'Missing fields'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Mobile number already exists'}), 400
        
    from werkzeug.security import generate_password_hash
    existing_truck_ids = [u.truck_id for u in User.query.filter_by(role='DRIVER').all() if u.truck_id is not None]
    next_truck_id = max(existing_truck_ids) + 1 if existing_truck_ids else 1
    
    new_driver = User(username=username, password_hash=generate_password_hash(password), role='DRIVER', truck_id=next_truck_id, name=name)
    db.session.add(new_driver)
    db.session.commit()
    
    return jsonify({'success': True, 'truck_id': next_truck_id})

@app.route('/api/admin_delete_driver/<int:driver_id>', methods=['DELETE'])
@login_required
def admin_delete_driver(driver_id):
    driver = db.session.get(User, driver_id)
    if not driver or driver.role != 'DRIVER':
        return jsonify({'error': 'Driver not found'}), 404

    if driver.assigned_template_id:
        old_inst = db.session.get(SavedTemplate, driver.assigned_template_id)
        if old_inst and getattr(old_inst, 'is_assigned_instance', False):
            db.session.delete(old_inst)

    try:
        id_token = get_firebase_token()
        if id_token:
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            import requests
            requests.delete(f"{firebase_url}/driver_locations/{driver.id}.json?auth={id_token}")
    except:
        pass
        
    db.session.delete(driver)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/assign_driver', methods=['POST'])
@login_required
def assign_driver():
    import json
    data = request.json or {}
    driver_id = data.get('driver_id')
    truck_id = data.get('truck_id')
    confirmations = data.get('confirmations') # optional dict
    
    if not truck_id:
        return jsonify({'error': 'Missing truck_id'}), 400
    try:
        truck_id = int(truck_id)
    except:
        return jsonify({'error': 'Invalid truck_id'}), 400
        
    if driver_id:
        try:
            driver = db.session.get(User, int(driver_id))
        except:
            driver = None
        if not driver or driver.role != 'DRIVER':
            return jsonify({'error': 'Driver not found'}), 404
            
        # Remove this truck_id from any other driver to prevent duplicates on the SAME truck
        User.query.filter(User.role == 'DRIVER', User.truck_id == truck_id, User.id != driver.id).update({'truck_id': None, 'assigned_template_id': None})
        driver.truck_id = truck_id
        
        # Dedicated assigned instance for this driver
        ws_meta = Metadata.query.filter_by(key='workspace_truck_ids').first()
        ws_trucks = []
        if ws_meta and ws_meta.value:
            try:
                ws_trucks = json.loads(ws_meta.value)
            except:
                ws_trucks = []

        curr = Metadata.query.filter_by(key='current_template_id').first()
        template_name = None
        if curr and curr.value and (not ws_trucks or truck_id in ws_trucks):
            try:
                master_t = db.session.get(SavedTemplate, int(curr.value))
            except:
                master_t = None
            if master_t:
                template_name = master_t.name
        if not template_name:
            curr_name_meta = Metadata.query.filter_by(key='current_template_name').first()
            if curr_name_meta and curr_name_meta.value:
                template_name = curr_name_meta.value
        if not template_name:
            template_name = f"Route - {driver.name or driver.username} (Truck {truck_id})"

        cust_rows = Customer.query.filter_by(truck_id=truck_id).order_by(Customer.stop_number.asc()).all()
        cust_list = [{
            'id': c.id, 'name': c.name, 'phone': c.phone, 'address': c.address,
            'location_url': c.location_url, 'lat': c.lat, 'lng': c.lng,
            'status': c.status, 'truck_id': 1, 'stop_number': c.stop_number,
            'confirmation': c.confirmation if c.confirmation else 'NOT_CONFIRMED',
            'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE'
        } for c in cust_rows]
        meta_rows = Metadata.query.all()
        meta_dict = {m.key: m.value for m in meta_rows}

        if driver.assigned_template_id:
            old_inst = db.session.get(SavedTemplate, driver.assigned_template_id)
            if old_inst and getattr(old_inst, 'is_assigned_instance', False):
                old_inst.name = template_name
                old_inst.metadata_json = json.dumps(meta_dict)
                old_inst.customers_json = json.dumps(cust_list)
            else:
                auto_t = SavedTemplate(
                    name=template_name,
                    metadata_json=json.dumps(meta_dict),
                    customers_json=json.dumps(cust_list),
                    is_assigned_instance=True
                )
                db.session.add(auto_t)
                db.session.flush()
                driver.assigned_template_id = auto_t.id
        else:
            auto_t = SavedTemplate(
                name=template_name,
                metadata_json=json.dumps(meta_dict),
                customers_json=json.dumps(cust_list),
                is_assigned_instance=True
            )
            db.session.add(auto_t)
            db.session.flush()
            driver.assigned_template_id = auto_t.id
    
    refused_cancel = []
    
    # Process confirmations if provided
    firebase_synced = True
    if confirmations is not None:
        customers_on_truck = Customer.query.filter_by(truck_id=truck_id).all()
        firebase_patch_data = {}
        
        for c in customers_on_truck:
            if c.id < 0: continue # Ignore depot rows
            if getattr(c, 'customer_status', 'ACTIVE') == 'INACTIVE': continue
            
            c_val = confirmations.get(str(c.id))
            if c_val not in ['CONFIRMED', 'NOT_CONFIRMED', 'CANCELLED']:
                c_val = 'NOT_CONFIRMED'
                
            if c_val == 'CANCELLED' and c.status == 'COMPLETED':
                refused_cancel.append(c.id)
                continue
                
            c.confirmation = c_val
            firebase_patch_data[f"{c.id}/confirmation"] = c_val
            
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
        if id_token:
            if confirmations is not None and firebase_patch_data:
                res = requests.patch(f"{firebase_url}/routes/route_{truck_id}/stops.json?auth={id_token}", json=firebase_patch_data)
                if res.status_code != 200:
                    firebase_synced = False
            if driver:
                requests.patch(f"{firebase_url}/trucks/{truck_id}.json?auth={id_token}", json={
                    "driverName": driver.name or driver.username,
                    "driverId": driver.id
                })
        else:
            firebase_synced = False
    except:
        firebase_synced = False
            
    db.session.commit()
    
    return jsonify({'success': True, 'firebase_synced': firebase_synced, 'refused_cancel': refused_cancel})



@app.route('/driver')
def driver_view():
    return render_template('driver_view.html')

def sync_firebase_to_sql(template_id=None):
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
        if not id_token:
            return
        
        # Determine which truck IDs we need to sync
        truck_ids_to_sync = None
        if template_id:
            drivers = User.query.filter_by(assigned_template_id=template_id).all()
            truck_ids_to_sync = [str(d.truck_id) for d in drivers] if drivers else []
        
        res = requests.get(f"{firebase_url}/routes.json?auth={id_token}", timeout=8)
        if res.status_code == 200:
            routes_data = res.json()
            if routes_data:
                for route_key, route_info in routes_data.items():
                    if not route_key.startswith('route_'): continue
                    tid_str = route_key.split('_')[1]
                    if truck_ids_to_sync is not None and tid_str not in truck_ids_to_sync:
                        continue
                    
                    try:
                        truck_id_int = int(tid_str)
                    except:
                        continue
                        
                    stops = route_info.get('stops')
                    if stops:
                        for stop_id_str, stop_data in stops.items():
                            try:
                                stop_id = int(stop_id_str)
                            except:
                                continue
                            
                            if stop_id < 0:
                                continue
                            
                            c = db.session.get(Customer, stop_id)
                            if c and c.truck_id == truck_id_int:
                                fb_status = stop_data.get('status')
                                fb_conf = stop_data.get('confirmation')
                                fb_cust_status = stop_data.get('customer_status')
                                fb_seq = stop_data.get('sequence')
                                
                                if fb_status and c.status != fb_status:
                                    c.status = fb_status
                                if fb_conf and c.confirmation != fb_conf:
                                    c.confirmation = fb_conf
                                if fb_cust_status and getattr(c, 'customer_status', None) != fb_cust_status:
                                    c.customer_status = fb_cust_status
                                if fb_seq is not None and c.stop_number != fb_seq:
                                    c.stop_number = fb_seq
                db.session.commit()
    except Exception as e:
        print("Error syncing Firebase to SQL inside get_data:", e)

@app.route('/api/data')
def get_data():
    template_id = request.args.get('template_id')
    req_truck_id = request.args.get('truck_id')
    
    # Sync LIVE data from Firebase to SQL before returning
    sync_firebase_to_sql(template_id)

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
        
    query = Customer.query
    if req_truck_id:
        try:
            query = query.filter(Customer.truck_id == int(req_truck_id))
        except:
            pass
    elif template_id:
        drivers = User.query.filter_by(assigned_template_id=template_id).all()
        truck_ids = [d.truck_id for d in drivers if d.truck_id is not None] if drivers else [-1]
        query = query.filter(Customer.truck_id.in_(truck_ids))
    elif 'workspace_truck_ids' in metadata and metadata['workspace_truck_ids']:
        try:
            ws_trucks = json.loads(metadata['workspace_truck_ids'])
            if ws_trucks and Customer.query.filter(Customer.truck_id.in_(ws_trucks)).count() > 0:
                query = query.filter(Customer.truck_id.in_(ws_trucks))
        except:
            pass
        
    customers_db = query.order_by(Customer.truck_id.asc(), Customer.stop_number.asc()).all()
    
    customers = []
    routes_dict = {}
    
    for r in customers_db:
        customers.append({
            'id': r.id, 'name': r.name, 'phone': r.phone, 'address': r.address,
            'location_url': r.location_url, 'lat': r.lat, 'lng': r.lng,
            'status': r.status, 'truck': r.truck_id, 'stop_number': r.stop_number,
            'confirmation': r.confirmation if r.confirmation else 'NOT_CONFIRMED',
            'customer_status': getattr(r, 'customer_status', 'ACTIVE') or 'ACTIVE'
        })
        t_id = r.truck_id
        if t_id not in routes_dict: routes_dict[t_id] = []
        routes_dict[t_id].append(r.id)
        
    routes = [routes_dict[t_id] for t_id in sorted(routes_dict.keys(), key=lambda x: x if x is not None else 999999)]
    
    route_times = []
    if 'route_times' in metadata:
        route_times = json.loads(metadata['route_times'])
        
    route_distances = []
    if 'route_distances' in metadata:
        route_distances = json.loads(metadata['route_distances'])
        
    driver_tokens = {}
    if 'driver_tokens' in metadata:
        driver_tokens = json.loads(metadata['driver_tokens'])

    drivers = User.query.filter_by(role='DRIVER').all()
    drivers_data = []
    for d in drivers:
        assigned_name = "No Route Assigned"
        if getattr(d, 'assigned_template_id', None):
            t = db.session.get(SavedTemplate, d.assigned_template_id)
            if t: assigned_name = t.name
            
        drivers_data.append({
            'id': d.id,
            'username': d.username,
            'name': d.name,
            'truck_id': d.truck_id,
            'assigned_template_id': getattr(d, 'assigned_template_id', None),
            'assigned_template_name': assigned_name
        })

    return jsonify({
        'customers': customers,
        'routes': routes,
        'route_times': route_times,
        'route_distances': route_distances,
        'start_coords': start_coords,
        'end_coords': end_coords,
        'driver_tokens': driver_tokens,
        'drivers': drivers_data,
        'is_from_template': metadata.get('is_from_template') == 'true',
        'current_template_id': metadata.get('current_template_id'),
        'current_template_name': metadata.get('current_template_name')
    })

@app.route('/api/mark_completed/<int:customer_id>', methods=['POST'])
def mark_completed(customer_id):
    customer = db.session.get(Customer, customer_id)
    if customer:
        customer.status = 'COMPLETED'
        db.session.commit()

        # Sync to Firebase
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            
            id_token = get_firebase_token()
            if id_token:
                requests.patch(f"{firebase_url}/routes/route_{customer.truck_id}/stops/{customer.id}.json?auth={id_token}", json={"status": "COMPLETED"})
        except Exception as e:
            print("Firebase sync error in mark_completed:", e)
            
    return jsonify({'success': True, 'status': 'COMPLETED'})

@app.route('/api/resolve_token')
def resolve_token():
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Missing token'}), 400
        
    try:
        user_id = int(token)
        driver = db.session.get(User, user_id)
        if driver and driver.role == 'DRIVER':
            return jsonify({
                'truck_id': str(driver.truck_id) if driver.truck_id is not None else None,
                'driver_name': driver.name or driver.username,
                'driver_id': driver.id
            })
    except ValueError:
        pass
        
    return jsonify({'error': 'Invalid or expired token'}), 404

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

@app.route('/api/remove_stop', methods=['POST'])
def remove_stop():
    data = request.json or {}
    cust_id = data.get('customer_id')
    raw_truck_id = data.get('truck_id')
    
    if cust_id is None or raw_truck_id is None:
        return jsonify({'error': 'Missing customer_id or truck_id'}), 400
        
    try:
        truck_id = int(raw_truck_id)
        cust_id = int(cust_id)
    except:
        return jsonify({'error': 'Invalid customer_id or truck_id'}), 400
        
    try:
        # Fetch target customer
        sql_cust = db.session.get(Customer, cust_id)
        if not sql_cust:
            return jsonify({'error': 'Customer not found in SQL database'}), 404
            
        target_seq = sql_cust.stop_number
        
        # Mark as cancelled (or delete)
        db.session.delete(sql_cust)
        
        # Shift subsequent stops in SQL
        if target_seq is not None:
            subsequent_stops = Customer.query.filter(
                Customer.truck_id == truck_id,
                Customer.stop_number > target_seq
            ).all()
            for s in subsequent_stops:
                s.stop_number -= 1
            
        db.session.commit()
        
        # Sync to Firebase
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
        if id_token:
            route_key = f"route_{truck_id}"
            
            stops_res = requests.get(f"{firebase_url}/routes/{route_key}/stops.json?auth={id_token}")
            stops = stops_res.json() or {}
            
            # Remove target stop and shift others
            if str(cust_id) in stops:
                del stops[str(cust_id)]
                
                for s_id, s_info in stops.items():
                    if s_info and target_seq is not None and s_info.get('sequence', 0) > target_seq:
                        s_info['sequence'] -= 1
                        
                # Update Firebase
                requests.put(f"{firebase_url}/routes/{route_key}/stops.json?auth={id_token}", json=stops)
                
        recompute_route_metrics()
        return jsonify({'success': True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_stop', methods=['POST'])
def add_stop():
    data = request.json
    if not data: return jsonify({'error': 'No data provided'}), 400
    
    name = data.get('name', 'New Stop')
    phone = data.get('phone', '')
    address = data.get('address', '')
    location_url = data.get('location_url', '')
    
    lat_val, lng_val = data.get('lat'), data.get('lng')
    if lat_val is not None and lng_val is not None:
        try: lat, lng = float(lat_val), float(lng_val)
        except ValueError: lat, lng = None, None
    else: lat, lng = None, None
    
    if lat is None or lng is None:
        if location_url:
            url_match = re.search(r'(https?://[^\s]+)', str(location_url))
            if url_match:
                lat, lng = resolve_gmaps_url(url_match.group(1))
            
    if lat is None and isinstance(lng, str):
        address = lng
        lng = None
        
    if (lat is None or lng is None) and address:
        search_query = str(address)
        if "ahmedabad" not in search_query.lower() and "gujarat" not in search_query.lower():
            search_query += ", Ahmedabad, Gujarat, India"
        gmaps_key = os.environ.get('GMAPS_API_KEY')
        if gmaps_key:
            try:
                import requests
                g_res = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params={'address': search_query, 'key': gmaps_key}).json()
                if g_res.get('status') == 'OK':
                    lat = g_res['results'][0]['geometry']['location']['lat']
                    lng = g_res['results'][0]['geometry']['location']['lng']
            except Exception as e: print(f"GMAPS Geocode Error: {e}")
        if lat is None or lng is None:
            try:
                from geopy.geocoders import Nominatim
                nom = Nominatim(user_agent="waste_route_optim_ahmedabad_1")
                parts = [p.strip() for p in search_query.split(',')]
                queries = [search_query]
                if len(parts) >= 5: queries.append(", ".join(parts[-5:]))
                if len(parts) >= 4: queries.append(", ".join(parts[-4:]))
                if len(parts) >= 3: queries.append(", ".join(parts[-3:]))
                if len(parts) >= 2: queries.append(", ".join(parts[-2:]))
                  
                # Progressive Nominatim (strict but accurate)
                for short_q in queries:
                    try:
                        print(f'NOM TRY: {short_q}')
                        loc = nom.geocode(short_q, timeout=3)
                        if loc:
                            lat, lng = loc.latitude, loc.longitude
                            break
                    except: pass
                      
                # If still none, fallback to progressive ArcGIS
                if lat is None or lng is None:
                    from geopy.geocoders import ArcGIS
                    arc = ArcGIS()
                    for short_q in queries:
                        try:
                            print(f'ARC TRY: {short_q}')
                            loc = arc.geocode(short_q, timeout=3)
                            if loc:
                                lat, lng = loc.latitude, loc.longitude
                                break
                        except: pass
            except: pass
        
    if lat is None or lng is None:
        return jsonify({'error': 'Could not resolve coordinates from the provided URL or Address.'}), 400
        
    try:
        max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
        new_id = max_id + 1
        
        insert_mode = data.get('insert_mode', 'auto')
        target_truck_id = data.get('target_truck_id')
        target_sequence = data.get('target_sequence', 0)
        
        if insert_mode == 'manual' and target_truck_id is not None:
            # Shift SQL sequences
            subsequent_stops = Customer.query.filter(
                Customer.truck_id == target_truck_id,
                Customer.stop_number > target_sequence).all()
            for s in subsequent_stops:
                s.stop_number += 1
                
            new_cust = Customer(
                id=new_id, name=name, phone=phone, address=address,
                location_url=location_url, lat=lat, lng=lng,
                status='PENDING', truck_id=target_truck_id, stop_number=target_sequence + 1,
                confirmation='NOT_CONFIRMED'
            )
            db.session.add(new_cust)
            db.session.commit()
            
            # Sync to Firebase
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            id_token = get_firebase_token()
            if id_token:
                route_key = f"route_{target_truck_id}"
                
                stops_res = requests.get(f"{firebase_url}/routes/{route_key}/stops.json?auth={id_token}")
                stops = stops_res.json() or {}
                
                # Shift sequence in firebase
                for s_id, s_info in stops.items():
                    if s_info and s_info.get('sequence', 0) > target_sequence:
                        s_info['sequence'] += 1
                
                # Add new stop
                stops[str(new_id)] = {
                    "name": name,
                    "address": address,
                    "phone": phone,
                    "lat": lat,
                    "lng": lng,
                    "sequence": target_sequence + 1,
                    "status": "PENDING",
                    "confirmation": "NOT_CONFIRMED",
                    "customer_status": "ACTIVE"
                }
                
                requests.put(f"{firebase_url}/routes/{route_key}/stops.json?auth={id_token}", json=stops)
                
            recompute_route_metrics()
            return jsonify({'success': True, 'customer_id': new_id})
            
        else:
            # Auto mode
            new_cust = Customer(
                id=new_id, name=name, phone=phone, address=address,
                location_url=location_url, lat=lat, lng=lng, status='PENDING',
                confirmation='NOT_CONFIRMED'
            )
            db.session.add(new_cust)
            db.session.commit()
            recompute_route_metrics()
            return jsonify({'success': True, 'customer_id': new_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/repair_database', methods=['POST'])
@login_required
def repair_database():
    try:
        data = request.json or {}
        dry_run = data.get('dry_run', True)
        
        # 1. Clean up Ghost Assignments (Drivers with assigned_template_id but no truck)
        ghost_drivers = User.query.filter(User.assigned_template_id != None, User.truck_id == None).all()
        ghost_count = len(ghost_drivers)
        ghost_details = [{"driver_id": d.id, "driver_name": d.name or d.username, "template_id": d.assigned_template_id} for d in ghost_drivers]
        
        if not dry_run:
            for d in ghost_drivers:
                d.assigned_template_id = None
            
        # 2. Re-sequence Customer stops sequentially per truck to fix any gaps
        distinct_trucks = db.session.query(Customer.truck_id).distinct().all()
        fixed_sequences = 0
        fixed_details = []
        for (truck_id,) in distinct_trucks:
            if truck_id is None: continue
            customers = Customer.query.filter_by(truck_id=truck_id).order_by(Customer.stop_number.asc()).all()
            for idx, c in enumerate(customers):
                correct_seq = idx + 1
                if c.stop_number != correct_seq:
                    fixed_details.append({"customer_id": c.id, "truck_id": truck_id, "old_seq": c.stop_number, "new_seq": correct_seq})
                    if not dry_run:
                        c.stop_number = correct_seq
                    fixed_sequences += 1
                    
        # 3. Purge completely orphaned Customers (truck_id is None)
        # Note: These might be unoptimized CSV uploads! 
        orphans = Customer.query.filter_by(truck_id=None).all()
        orphan_count = len(orphans)
        orphan_details = [{"customer_id": o.id, "name": o.name, "status": o.status} for o in orphans]
        
        if not dry_run:
            for o in orphans:
                db.session.delete(o)
                
        if not dry_run:
            db.session.commit()
            return jsonify({
                'success': True,
                'message': f"Database repaired: Cleared {ghost_count} ghost route assignments, fixed {fixed_sequences} stop sequences, and purged {orphan_count} orphaned customers.",
                'details': { 'ghosts': ghost_details, 'sequences': fixed_details, 'orphans': orphan_details }
            })
        else:
            db.session.rollback() # Ensure nothing was saved
            return jsonify({
                'success': True,
                'dry_run': True,
                'message': f"Dry run complete. Would clear {ghost_count} ghost route assignments, fix {fixed_sequences} stop sequences, and purge {orphan_count} orphaned customers.",
                'details': { 'ghosts': ghost_details, 'sequences': fixed_details, 'orphans': orphan_details }
            })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)




@app.route('/api/ai_rebalance', methods=['POST'])
@login_required
def ai_rebalance():
    import requests
    import json
    
    # 1. Fetch current GPS from Firebase
    firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
    id_token = get_firebase_token()
    if not id_token:
        return jsonify({'error': 'Firebase auth failed'}), 500
        
    trucks_res = requests.get(f"{firebase_url}/trucks.json?auth={id_token}")
    trucks_data = trucks_res.json() if trucks_res.status_code == 200 and trucks_res.json() else {}
    
    # 2. Get original metadata for fallback start/end coords
    metadata_rows = Metadata.query.all()
    metadata = {row.key: row.value for row in metadata_rows}
    
    if 'start_coords' in metadata:
        original_starts = json.loads(metadata['start_coords'])
    else:
        return jsonify({'error': 'No original start locations found to determine fleet size'}), 400
        
    if 'end_coords' in metadata:
        original_ends = json.loads(metadata['end_coords'])
    else:
        original_ends = []
        
    start_coords = []
    end_coords = []
    
    num_trucks = len(original_starts)
    
    # 3. Build live start coords based on Firebase GPS (if available), else fallback to original
    for i in range(num_trucks):
        truck_id_str = str(i + 1)
        lat = float(original_starts[i][0])
        lng = float(original_starts[i][1])
        
        # Override with live GPS if available and truck is not offline
        if truck_id_str in trucks_data:
            t = trucks_data[truck_id_str]
            if t.get('currentLat') and t.get('currentLng'): # Always use their last known position
                lat = float(t['currentLat'])
                lng = float(t['currentLng'])
                
        start_coords.append((lat, lng))
        
        if original_ends and len(original_ends) > i:
            end_coords.append((float(original_ends[i][0]), float(original_ends[i][1])))
        elif original_ends:
            end_coords.append((float(original_ends[0][0]), float(original_ends[0][1])))
            
    # 4. Get all PENDING stops (exclude Depot -1000)
    pending_customers = Customer.query.filter(Customer.status == 'PENDING', Customer.id > -1000).all()
    if not pending_customers:
        return jsonify({'error': 'No pending stops to rebalance'}), 400
        
    customers_data = [{
        'id': c.id, 'name': c.name, 'phone': c.phone, 'address': c.address,
        'location_url': c.location_url, 'lat': c.lat, 'lng': c.lng
    } for c in pending_customers if c.confirmation != 'CANCELLED']
    
    cancelled_customers = [c for c in pending_customers if c.confirmation == 'CANCELLED']
    cancelled_by_truck = {}
    for c in cancelled_customers:
        tid = c.truck_id or 1
        if tid not in cancelled_by_truck: cancelled_by_truck[tid] = []
        cancelled_by_truck[tid].append(c)
    
    # 5. Run AI
    aco = ACO_VRP(start_coords, end_coords, customers_data, num_trucks=num_trucks)
    routes, route_times, route_distances = aco.run()
    
    active_routes = []
    active_route_times = []
    active_route_distances = []
    for r, t, d in zip(routes, route_times, route_distances):
        if len(r) > 0:
            active_routes.append(r)
            active_route_times.append(t)
            active_route_distances.append(d)
            
    # 6. Apply new routes to DB
    # First, clear truck assignments for all pending stops
    for c in pending_customers:
        c.truck_id = None
        c.stop_number = None
        
    routes_payload = {}
    
    for truck_idx, route in enumerate(active_routes):
        truck_id = truck_idx + 1
        route_key = f"route_{truck_id}"
        routes_payload[route_key] = {}
        
        for stop_num, cid in enumerate(route):
            for c in pending_customers:
                if c.id == cid:
                    c.truck_id = truck_id
                    c.stop_number = stop_num + 1
                    
                    routes_payload[route_key][str(cid)] = {
                        "name": c.name,
                        "address": c.address,
                        "phone": c.phone or '',
                        "lat": c.lat,
                        "lng": c.lng,
                        "sequence": stop_num + 1,
                        "status": "PENDING",
                        "confirmation": c.confirmation or "NOT_CONFIRMED",
                        "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
                    }
                    
        # Append cancelled customers
        if truck_id in cancelled_by_truck:
            for c in cancelled_by_truck[truck_id]:
                stop_num = len(route)
                c.truck_id = truck_id
                c.stop_number = stop_num + 1
                
                routes_payload[route_key][str(c.id)] = {
                    "name": c.name,
                    "address": c.address,
                    "phone": c.phone or '',
                    "lat": c.lat,
                    "lng": c.lng,
                    "sequence": stop_num + 1,
                    "status": c.status,
                    "confirmation": "CANCELLED",
                    "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
                }
                route.append(c.id)
                
        # Append End Location as the final stop
        if end_coords:
            end_idx = min(truck_idx, len(end_coords) - 1)
            depot_lat, depot_lng = end_coords[end_idx]
            
            # Check if depot exists
            depot_cid = -1000 - truck_idx
            depot_c = db.session.get(Customer, depot_cid)
            if not depot_c:
                depot_c = Customer(
                    id=depot_cid, name='End Location / Depot', address='Return to Depot',
                    lat=depot_lat, lng=depot_lng, status='PENDING'
                )
                db.session.add(depot_c)
                
            depot_c.truck_id = truck_id
            depot_c.stop_number = len(route) + 1
            
            routes_payload[route_key][str(depot_cid)] = {
                "name": depot_c.name,
                "address": depot_c.address,
                "phone": '',
                "lat": depot_c.lat,
                "lng": depot_c.lng,
                "sequence": len(route) + 1,
                "status": "PENDING",
                "confirmation": "NOT_CONFIRMED",
                "customer_status": "ACTIVE"
            }
            
    # Update Metadata with new times and distances
    m_times = Metadata.query.filter_by(key='route_times').first()
    if m_times: m_times.value = json.dumps(active_route_times)
    m_dist = Metadata.query.filter_by(key='route_distances').first()
    if m_dist: m_dist.value = json.dumps(active_route_distances)
    
    db.session.commit()
    
    # Add back COMPLETED stops so driver apps keep their historical progress for the day
    completed_customers = Customer.query.filter(Customer.status == 'COMPLETED').all()
    for c in completed_customers:
        if c.truck_id:
            route_key = f"route_{c.truck_id}"
            if route_key not in routes_payload: routes_payload[route_key] = {}
            routes_payload[route_key][str(c.id)] = {
                "name": c.name,
                "address": c.address,
                "phone": c.phone or '',
                "lat": c.lat,
                "lng": c.lng,
                "sequence": c.stop_number,
                "status": "COMPLETED",
                "confirmation": c.confirmation or "NOT_CONFIRMED",
                "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
            }

    # 7. Push to Firebase
    requests.delete(f"{firebase_url}/routes.json?auth={id_token}")
    for route_key, stops in routes_payload.items():
        requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops})
        
    recompute_route_metrics()
    return jsonify({'success': True})

@app.route('/api/update_route_manual', methods=['POST'])
@login_required
def update_route_manual():
    data = request.json.get('routes', {})
    
    customers = Customer.query.all()
    cust_map = {c.id: c for c in customers}
    
    routes_payload = {}
    
    for truck_id, stop_ids in data.items():
        truck_id_int = int(truck_id)
        route_key = f"route_{truck_id_int}"
        if route_key not in routes_payload:
            routes_payload[route_key] = {}
        
        # Re-sequence the valid customers based on their new index
        for idx, cid in enumerate(stop_ids):
            if cid in cust_map:
                c = cust_map[cid]
                c.truck_id = truck_id_int
                c.stop_number = idx + 1
                
                routes_payload[route_key][str(cid)] = {
                    "name": c.name,
                    "address": c.address,
                    "phone": c.phone or '',
                    "lat": c.lat,
                    "lng": c.lng,
                    "sequence": idx + 1,
                    "status": c.status,
                    "confirmation": c.confirmation or "NOT_CONFIRMED",
                    "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
                }
                
        # Preserve depot stop for this truck
        depot_stops = [c for c in customers if c.truck_id == truck_id_int and (c.id <= -1000 or c.name == 'End Location / Depot')]
        for dc in depot_stops:
            dc.stop_number = len(stop_ids) + 1
            routes_payload[route_key][str(dc.id)] = {
                "name": dc.name,
                "address": dc.address,
                "phone": '',
                "lat": dc.lat,
                "lng": dc.lng,
                "sequence": dc.stop_number,
                "status": dc.status or "PENDING",
                "confirmation": "NOT_CONFIRMED",
                "customer_status": "ACTIVE"
            }
                
    db.session.commit()
    
    # Sync with Firebase (only update the modified routes, preserving other drivers' routes)
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
        if id_token:
            for route_key, stops in routes_payload.items():
                requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops})
    except Exception as e:
        print("Firebase sync error on manual reorder:", e)
        
    recompute_route_metrics()
    return jsonify({'success': True})


@app.route('/api/update_customer_status', methods=['POST'])
@login_required
def update_customer_status():
    data = request.json
    cust_id = data.get('id')
    status = data.get('customer_status')
    
    if not cust_id or not status:
        return jsonify({'error': 'Missing parameters'}), 400
        
    try:
        cust_id = int(cust_id)
    except:
        return jsonify({'error': 'Invalid customer id'}), 400
        
    c = db.session.get(Customer, cust_id)
    if not c:
        return jsonify({'error': 'Customer not found'}), 404
        
    try:
        c.customer_status = status
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'DB Error: {str(e)}'}), 500
        
    # Check if assigned to an active route
    if c.truck_id and c.stop_number:
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            id_token = get_firebase_token()
            if id_token:
                payload = { "customer_status": status }
                requests.patch(f"{firebase_url}/routes/route_{c.truck_id}/stops/{c.id}.json?auth={id_token}", json=payload)
        except Exception as e:
            print("Firebase sync error in update_customer_status:", e)
            
    return jsonify({'success': True})

@app.route('/api/assign_route', methods=['POST'])
@login_required
def assign_route():
    data = request.json or {}
    driver_id = data.get('driver_id')
    template_id = data.get('template_id')
    requested_truck_id = data.get('truck_id')
    
    driver = None
    if driver_id:
        try:
            driver = db.session.get(User, int(driver_id))
        except:
            driver = None
    if not driver: return jsonify({'error': 'Driver not found'}), 404
    
    # Determine other drivers' active trucks
    other_active_trucks = set()
    for od in User.query.filter(User.role == 'DRIVER', User.id != driver.id, User.assigned_template_id != None, User.truck_id != None).all():
        if Customer.query.filter(Customer.truck_id == od.truck_id, Customer.id > -1000, Customer.status == 'PENDING').count() > 0:
            other_active_trucks.add(int(od.truck_id))

    if requested_truck_id:
        try:
            truck_id_int = int(requested_truck_id)
        except:
            truck_id_int = 1
        if truck_id_int in other_active_trucks:
            truck_id_int = 1
            while truck_id_int in other_active_trucks:
                truck_id_int += 1
        User.query.filter(User.role == 'DRIVER', User.truck_id == truck_id_int, User.id != driver.id).update({'truck_id': None})
        driver.truck_id = truck_id_int
        db.session.commit()
    elif not driver.truck_id or int(driver.truck_id) in other_active_trucks:
        truck_id_int = 1
        while truck_id_int in other_active_trucks:
            truck_id_int += 1
        User.query.filter(User.role == 'DRIVER', User.truck_id == truck_id_int, User.id != driver.id).update({'truck_id': None})
        driver.truck_id = truck_id_int
        db.session.commit()
        
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
    except:
        id_token = None
    
    if not template_id:
        if driver.assigned_template_id:
            old_inst = db.session.get(SavedTemplate, driver.assigned_template_id)
            if old_inst and getattr(old_inst, 'is_assigned_instance', False):
                db.session.delete(old_inst)
        driver.assigned_template_id = None
        Customer.query.filter_by(truck_id=driver.truck_id).delete()
        db.session.commit()
        if id_token:
            requests.delete(f"{firebase_url}/routes/route_{driver.truck_id}.json?auth={id_token}")
        recompute_route_metrics()
        return jsonify({'success': True})
        
    try:
        t = db.session.get(SavedTemplate, int(template_id))
    except:
        t = None
    if not t: return jsonify({'error': 'Template not found'}), 404
    
    # Create or update dedicated assigned instance for this driver
    if driver.assigned_template_id:
        old_inst = db.session.get(SavedTemplate, driver.assigned_template_id)
        if old_inst and getattr(old_inst, 'is_assigned_instance', False):
            old_inst.name = t.name
            old_inst.metadata_json = t.metadata_json
            old_inst.customers_json = t.customers_json
            assigned_inst = old_inst
        else:
            assigned_inst = SavedTemplate(
                name=t.name,
                metadata_json=t.metadata_json,
                customers_json=t.customers_json,
                is_assigned_instance=True
            )
            db.session.add(assigned_inst)
            db.session.flush()
    else:
        assigned_inst = SavedTemplate(
            name=t.name,
            metadata_json=t.metadata_json,
            customers_json=t.customers_json,
            is_assigned_instance=True
        )
        db.session.add(assigned_inst)
        db.session.flush()

    driver.assigned_template_id = assigned_inst.id
    Customer.query.filter_by(truck_id=driver.truck_id).delete()
    
    import json
    cust_list = json.loads(t.customers_json or '[]')
    
    existing_ids = set(r[0] for r in db.session.query(Customer.id).all())
    max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
    if max_id < 0:
        max_id = 0

    for c in cust_list:
        raw_id = int(c['id'])
        if raw_id <= -1000 or c.get('name') == 'End Location / Depot':
            cid = -1000 - int(driver.truck_id)
            if cid in existing_ids:
                Customer.query.filter_by(id=cid).delete()
        else:
            cid = raw_id
            if cid in existing_ids:
                max_id += 1
                cid = max_id
        existing_ids.add(cid)
        new_cust = Customer(
            id=cid, name=c['name'], phone=c.get('phone'), address=c.get('address'),
            location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
            status='PENDING', truck_id=driver.truck_id, stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
            customer_status=c.get('customer_status', 'ACTIVE')
        )
        db.session.add(new_cust)
        
    db.session.commit()
    
    if id_token:
        try:
            new_custs = Customer.query.filter_by(truck_id=driver.truck_id).all()
            if new_custs:
                route_key = f"route_{driver.truck_id}"
                stops_payload = {}
                for c in new_custs:
                    stops_payload[str(c.id)] = {
                        "name": c.name,
                        "address": c.address,
                        "phone": c.phone or '',
                        "lat": c.lat,
                        "lng": c.lng,
                        "sequence": c.stop_number,
                        "status": "PENDING",
                        "confirmation": c.confirmation,
                        "customer_status": getattr(c, 'customer_status', 'ACTIVE')
                    }
                requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops_payload})
                requests.patch(f"{firebase_url}/trucks/{driver.truck_id}.json?auth={id_token}", json={
                    "status": "offline",
                    "driverName": driver.name or driver.username,
                    "driverId": driver.id
                })
        except Exception as e:
            print("Firebase sync error assigning:", e)
            
    recompute_route_metrics()
    return jsonify({'success': True})

@app.route('/api/save_template', methods=['POST'])
@login_required
def save_template():
    data = request.json or {}
    name = data.get('name')
    t_id = data.get('id')
    is_edit_assigned = data.get('is_edit_assigned', False)
    if not name: return jsonify({'error': 'Name is required'}), 400
    
    import json
    
    # Dump Metadata
    meta_rows = Metadata.query.all()
    meta_dict = {m.key: m.value for m in meta_rows}
    
    ws_trucks = []
    if 'workspace_truck_ids' in meta_dict and meta_dict['workspace_truck_ids']:
        try:
            ws_trucks = json.loads(meta_dict['workspace_truck_ids'])
        except:
            ws_trucks = []
            
    # Check if target is an assigned instance or master library template
    target_is_assigned = False
    t = None
    if t_id:
        try:
            t = db.session.get(SavedTemplate, int(t_id))
        except:
            t = None
        if t and getattr(t, 'is_assigned_instance', False):
            target_is_assigned = True
    if is_edit_assigned:
        target_is_assigned = True
    
    # Dump Customers (only for the target template or current workspace, never mixing other drivers' routes)
    cust_rows = None
    if target_is_assigned and t:
        drivers = User.query.filter_by(assigned_template_id=t.id).all()
        if drivers:
            truck_ids = [d.truck_id for d in drivers if d.truck_id is not None]
            if truck_ids:
                cust_rows = Customer.query.filter(Customer.truck_id.in_(truck_ids)).order_by(Customer.truck_id.asc(), Customer.stop_number.asc()).all()
    if cust_rows is None:
        if ws_trucks:
            cust_rows = Customer.query.filter(Customer.truck_id.in_(ws_trucks)).order_by(Customer.truck_id.asc(), Customer.stop_number.asc()).all()
        else:
            protected_trucks = get_active_assigned_trucks()
            if protected_trucks:
                cust_rows = Customer.query.filter((Customer.truck_id == None) | (~Customer.truck_id.in_(list(protected_trucks)))).order_by(Customer.truck_id.asc(), Customer.stop_number.asc()).all()
            else:
                cust_rows = Customer.query.order_by(Customer.truck_id.asc(), Customer.stop_number.asc()).all()
            
    cust_list = [{
        'id': c.id, 'name': c.name, 'phone': c.phone, 'address': c.address,
        'location_url': c.location_url, 'lat': c.lat, 'lng': c.lng,
        'status': c.status, 'truck_id': c.truck_id, 'stop_number': c.stop_number,
        'confirmation': c.confirmation if c.confirmation else 'NOT_CONFIRMED',
        'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE'
    } for c in cust_rows]
    
    if not t and not target_is_assigned:
        t = SavedTemplate.query.filter(
            SavedTemplate.name == name,
            (SavedTemplate.is_assigned_instance == False) | (SavedTemplate.is_assigned_instance == None)
        ).first()
        
    if t:
        t.name = name
        t.metadata_json = json.dumps(meta_dict)
        t.customers_json = json.dumps(cust_list)
        t.created_at = db.func.now()
    else:
        t = SavedTemplate(
            name=name,
            metadata_json=json.dumps(meta_dict),
            customers_json=json.dumps(cust_list),
            is_assigned_instance=target_is_assigned
        )
        db.session.add(t)
    db.session.commit()
    
    if not target_is_assigned:
        # Update current_template_id and current_template_name in Metadata so subsequent driver assignment links to this template
        curr_id_meta = Metadata.query.filter_by(key='current_template_id').first()
        if not curr_id_meta:
            curr_id_meta = Metadata(key='current_template_id')
            db.session.add(curr_id_meta)
        curr_id_meta.value = str(t.id)
        
        curr_name_meta = Metadata.query.filter_by(key='current_template_name').first()
        if not curr_name_meta:
            curr_name_meta = Metadata(key='current_template_name')
            db.session.add(curr_name_meta)
        curr_name_meta.value = str(t.name)
        db.session.commit()
    
    # Auto-sync to drivers and Firebase ONLY if this is an assigned route instance
    if target_is_assigned:
        affected_drivers = User.query.filter_by(assigned_template_id=t.id).all()
        if affected_drivers:
            try:
                import requests
                firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
                id_token = get_firebase_token()
            except:
                id_token = None
                
            for d in affected_drivers:
                if not d.truck_id:
                    continue
                Customer.query.filter_by(truck_id=d.truck_id).delete()
                db.session.flush()
                existing_ids = set(r[0] for r in db.session.query(Customer.id).all())
                max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
                if max_id < 0:
                    max_id = 0
                    
                for c in cust_list:
                    raw_id = int(c['id'])
                    if raw_id <= -1000 or c.get('name') == 'End Location / Depot':
                        cid = -1000 - int(d.truck_id)
                        if cid in existing_ids:
                            Customer.query.filter_by(id=cid).delete()
                    else:
                        cid = raw_id
                        if cid in existing_ids:
                            max_id += 1
                            cid = max_id
                    existing_ids.add(cid)
                    new_cust = Customer(
                        id=cid, name=c['name'], phone=c.get('phone'), address=c.get('address'),
                        location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
                        status=c.get('status', 'PENDING'), truck_id=d.truck_id, stop_number=c.get('stop_number'),
                        confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
                        customer_status=c.get('customer_status', 'ACTIVE')
                    )
                    db.session.add(new_cust)
                db.session.commit()
                
                if id_token:
                    try:
                        new_custs = Customer.query.filter_by(truck_id=d.truck_id).all()
                        if new_custs:
                            route_key = f"route_{d.truck_id}"
                            stops_payload = {}
                            for c in new_custs:
                                stops_payload[str(c.id)] = {
                                    "name": c.name,
                                    "address": c.address,
                                    "phone": c.phone or '',
                                    "lat": c.lat,
                                    "lng": c.lng,
                                    "sequence": c.stop_number,
                                    "status": c.status,
                                    "confirmation": c.confirmation,
                                    "customer_status": getattr(c, 'customer_status', 'ACTIVE')
                                }
                            requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops_payload})
                    except Exception as e:
                        print("Firebase sync error on template save:", e)
            recompute_route_metrics()
    
    return jsonify({'success': True})

@app.route('/api/templates', methods=['GET'])
@login_required
def get_templates():
    try:
        templates = SavedTemplate.query.filter(
            (SavedTemplate.is_assigned_instance == False) | (SavedTemplate.is_assigned_instance == None)
        ).order_by(SavedTemplate.created_at.desc()).all()
    except Exception as e:
        db.session.rollback()
        from sqlalchemy import text
        try:
            db.session.execute(text("ALTER TABLE saved_templates ADD COLUMN is_assigned_instance BOOLEAN DEFAULT FALSE;"))
            db.session.commit()
            templates = SavedTemplate.query.filter(
                (SavedTemplate.is_assigned_instance == False) | (SavedTemplate.is_assigned_instance == None)
            ).order_by(SavedTemplate.created_at.desc()).all()
        except:
            db.session.rollback()
            try:
                templates = SavedTemplate.query.order_by(SavedTemplate.created_at.desc()).all()
            except:
                db.session.rollback()
                templates = []
    res = []
    for t in templates:
        res.append({
            'id': t.id,
            'name': t.name,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S') if t.created_at else ''
        })
    return jsonify({'success': True, 'templates': res})

@app.route('/api/assigned_routes', methods=['GET'])
@login_required
def get_assigned_routes():
    # Sync latest completion statuses from Firebase
    try:
        sync_firebase_to_sql()
    except Exception as e:
        print("sync_firebase_to_sql error in get_assigned_routes:", e)

    # Only return routes for drivers who actually have a truck assigned
    drivers = User.query.filter(User.assigned_template_id != None, User.truck_id != None).all()
    
    res = []
    for d in drivers:
        try:
            t = db.session.get(SavedTemplate, d.assigned_template_id)
        except Exception as e:
            db.session.rollback()
            t = None
        if not t:
            d.assigned_template_id = None
            continue

        # Real stops for this truck
        total_stops = Customer.query.filter(Customer.truck_id == d.truck_id, Customer.id > -1000).count()
        pending_stops = Customer.query.filter(Customer.truck_id == d.truck_id, Customer.id > -1000, Customer.status == 'PENDING').count()
        
        # Self-heal / recover if stops were missing from Customer table
        if total_stops == 0 and t and t.customers_json:
            import json
            try:
                t_custs = json.loads(t.customers_json or '[]')
            except:
                t_custs = []
            if len(t_custs) > 0:
                for c in t_custs:
                    new_cust = Customer(
                        id=int(c['id']), name=c['name'], phone=c.get('phone'), address=c.get('address'),
                        location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
                        status=c.get('status', 'PENDING'), truck_id=d.truck_id, stop_number=c.get('stop_number'),
                        confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
                        customer_status=c.get('customer_status', 'ACTIVE')
                    )
                    db.session.add(new_cust)
                db.session.commit()
                total_stops = Customer.query.filter(Customer.truck_id == d.truck_id, Customer.id > -1000).count()
                pending_stops = Customer.query.filter(Customer.truck_id == d.truck_id, Customer.id > -1000, Customer.status == 'PENDING').count()

        # If all stops on the route are completed or skipped (0 pending left):
        # The route is finished! Automatically clear the driver's assignment so it disappears from Assigned Routes!
        if total_stops > 0 and pending_stops == 0:
            if d.assigned_template_id:
                old_inst = db.session.get(SavedTemplate, d.assigned_template_id)
                if old_inst and getattr(old_inst, 'is_assigned_instance', False):
                    db.session.delete(old_inst)
            d.assigned_template_id = None
            continue

        res.append({
            'id': t.id,
            'name': t.name,
            'stops_count': total_stops,
            'pending_stops_count': pending_stops,
            'driver_name': d.name or d.username,
            'truck_id': d.truck_id,
            'truck_ids': [d.truck_id]
        })
        
    db.session.commit()
    return jsonify({'success': True, 'assigned_routes': res})

@app.route('/api/unassign_route', methods=['POST'])
@login_required
def unassign_route():
    data = request.json or {}
    template_id = data.get('template_id')
    truck_id = data.get('truck_id')
    
    drivers = []
    if truck_id:
        try: drivers = User.query.filter_by(truck_id=int(truck_id)).all()
        except: pass
    if not drivers and template_id:
        try: drivers = User.query.filter_by(assigned_template_id=int(template_id)).all()
        except: pass
        
    for d in drivers:
        if d.assigned_template_id:
            old_inst = db.session.get(SavedTemplate, d.assigned_template_id)
            if old_inst and getattr(old_inst, 'is_assigned_instance', False):
                db.session.delete(old_inst)
        d.assigned_template_id = None
        if d.truck_id:
            Customer.query.filter_by(truck_id=d.truck_id).delete()
    db.session.commit()
    
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
        if id_token:
            for d in drivers:
                if d.truck_id:
                    requests.delete(f"{firebase_url}/routes/route_{d.truck_id}.json?auth={id_token}")
                    requests.patch(f"{firebase_url}/trucks/{d.truck_id}.json?auth={id_token}", json={
                        "driverName": None,
                        "driverId": None,
                        "status": "offline"
                    })
    except Exception as e:
        print("Firebase unassign error:", e)
        
    recompute_route_metrics()
    return jsonify({'success': True})

@app.route('/api/driver_finish_route', methods=['POST'])
def driver_finish_route():
    data = request.json or {}
    truck_id = data.get('truck_id')
    driver_id = data.get('driver_id')
    
    driver = None
    if driver_id:
        try: driver = db.session.get(User, int(driver_id))
        except: pass
    if not driver and truck_id:
        try: driver = User.query.filter_by(role='DRIVER', truck_id=int(truck_id)).first()
        except: pass
        
    if driver:
        if driver.assigned_template_id:
            old_inst = db.session.get(SavedTemplate, driver.assigned_template_id)
            if old_inst and getattr(old_inst, 'is_assigned_instance', False):
                db.session.delete(old_inst)
        driver.assigned_template_id = None
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Driver not found'}), 404

@app.route('/api/delete_template/<int:t_id>', methods=['DELETE'])
@login_required
def delete_template(t_id):
    t = db.session.get(SavedTemplate, t_id)
    if t:
        User.query.filter_by(assigned_template_id=t_id).update({'assigned_template_id': None})
        db.session.delete(t)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/deploy_template/<int:t_id>', methods=['POST'])
@login_required
def deploy_template(t_id):
    mode = request.args.get('mode', 'deploy')
    t = db.session.get(SavedTemplate, t_id)
    if not t: return jsonify({'error': 'Template not found'}), 404
    
    import json
    meta_dict = json.loads(t.metadata_json or '{}')
    cust_list = json.loads(t.customers_json or '[]')
    
    # Protect trucks that are currently assigned to active drivers
    protected_trucks = get_active_assigned_trucks()
    if protected_trucks:
        Customer.query.filter((Customer.truck_id == None) | (~Customer.truck_id.in_(list(protected_trucks)))).delete(synchronize_session=False)
    else:
        Customer.query.delete()
    Metadata.query.delete()
    
    # Remap template truck IDs so they never collide with protected active trucks
    orig_trucks = sorted(list(set(int(c.get('truck_id') or 1) for c in cust_list)))
    if not orig_trucks:
        orig_trucks = [1]
    used_trucks = set(protected_trucks)
    truck_id_map = {}
    for orig_tid in orig_trucks:
        new_tid = orig_tid
        if new_tid in used_trucks:
            new_tid = 1
            while new_tid in used_trucks:
                new_tid += 1
        truck_id_map[orig_tid] = new_tid
        used_trucks.add(new_tid)
        
    workspace_trucks = sorted(list(truck_id_map.values()))
    
    for k, v in meta_dict.items():
        if k not in ['is_from_template', 'current_template_id', 'current_template_name', 'workspace_truck_ids']:
            db.session.add(Metadata(key=k, value=v))
            
    is_template_val = 'true' if mode == 'deploy' else 'false'
    db.session.add(Metadata(key='is_from_template', value=is_template_val))
    db.session.add(Metadata(key='current_template_id', value=str(t.id)))
    db.session.add(Metadata(key='current_template_name', value=str(t.name)))
    db.session.add(Metadata(key='workspace_truck_ids', value=json.dumps(workspace_trucks)))
        
    existing_ids = set(r[0] for r in db.session.query(Customer.id).all())
    max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
    if max_id < 0:
        max_id = 0
        
    deployed_customers = []
    for c in cust_list:
        orig_tid = int(c.get('truck_id') or 1)
        new_tid = truck_id_map.get(orig_tid, orig_tid)
        raw_id = int(c['id'])
        if raw_id <= -1000 or c.get('name') == 'End Location / Depot':
            cid = -1000 - new_tid
            if cid in existing_ids:
                Customer.query.filter_by(id=cid).delete()
        else:
            cid = raw_id
            if cid in existing_ids:
                max_id += 1
                cid = max_id
        existing_ids.add(cid)
        
        new_cust = Customer(
            id=cid, name=c['name'], phone=c.get('phone'), address=c.get('address'),
            location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
            status='PENDING', truck_id=new_tid, stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
            customer_status=c.get('customer_status', 'ACTIVE')
        )
        db.session.add(new_cust)
        deployed_customers.append({
            'id': cid,
            'name': c['name'],
            'address': c.get('address', ''),
            'phone': c.get('phone', ''),
            'lat': c['lat'],
            'lng': c['lng'],
            'truck_id': new_tid,
            'stop_number': c.get('stop_number'),
            'confirmation': c.get('confirmation', 'NOT_CONFIRMED'),
            'customer_status': c.get('customer_status', 'ACTIVE')
        })
        
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Database error during deploy: {str(e)}'}), 200
    
    # Sync with Firebase immediately while preserving protected active routes (only when deploying, NOT when opening to edit)
    if mode == 'deploy':
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            id_token = get_firebase_token()
            if id_token:
                
                # Only remove non-protected routes in Firebase
                routes_res = requests.get(f"{firebase_url}/routes.json?auth={id_token}")
                if routes_res.status_code == 200 and routes_res.json():
                    routes_data = routes_res.json()
                    routes_items = routes_data.items() if isinstance(routes_data, dict) else enumerate(routes_data) if isinstance(routes_data, list) else []
                    for rid, val in routes_items:
                        if val is not None:
                            try:
                                tid_num = int(str(rid).replace('route_', ''))
                                if tid_num in protected_trucks:
                                    continue
                            except:
                                pass
                            requests.delete(f"{firebase_url}/routes/{rid}.json?auth={id_token}")
                
                routes_payload = {}
                for c in deployed_customers:
                    tid = c.get('truck_id')
                    if tid:
                        route_key = f"route_{tid}"
                        if route_key not in routes_payload: routes_payload[route_key] = {}
                        
                        routes_payload[route_key][str(c['id'])] = {
                            "name": c['name'],
                            "address": c['address'],
                            "phone": c.get('phone', ''),
                            "lat": c['lat'],
                            "lng": c['lng'],
                            "sequence": c.get('stop_number'),
                            "status": "PENDING",
                            "confirmation": c.get("confirmation", "NOT_CONFIRMED"),
                            "customer_status": c.get("customer_status", "ACTIVE")
                        }
                        
                for route_key, stops in routes_payload.items():
                    requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops})
                    tid = route_key.split('_')[1]
                    requests.put(f"{firebase_url}/trucks/{tid}.json?auth={id_token}", json={"status": "offline"})
        except Exception as e:
            print("Deploy Firebase error:", e)
        
    recompute_route_metrics()
    return jsonify({'success': True})

@app.route('/api/dynamic_recalculate', methods=['POST'])
def dynamic_recalculate():
    import requests
    firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
    
    try:
        # Authenticate anonymously as backend
        id_token = get_firebase_token()
        if not id_token:
            return jsonify({'error': 'Backend auth failed'}), 500
        
        # 1. Fetch current GPS for all trucks
        trucks_res = requests.get(f"{firebase_url}/trucks.json?auth={id_token}")
        trucks_data = trucks_res.json() or {}
        
        # 2. Fetch all current routes
        routes_res = requests.get(f"{firebase_url}/routes.json?auth={id_token}")
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
                                'phone': stop_info.get('phone', ''),
                                'lat': float(stop_info['lat']),
                                'lng': float(stop_info['lng']),
                                'confirmation': stop_info.get('confirmation', 'NOT_CONFIRMED'),
                                'customer_status': stop_info.get('customer_status', 'ACTIVE'),
                                'truck_id': truck_id,
                                'status': stop_info.get('status', 'PENDING')
                            })
                            
        unassigned = Customer.query.filter_by(status='PENDING').filter(Customer.truck_id == None).all()
        for c in unassigned:
            pending_customers.append({
                'id': str(c.id),
                'name': c.name,
                'address': c.address,
                'phone': c.phone,
                'lat': c.lat,
                'lng': c.lng,
                'confirmation': c.confirmation or 'NOT_CONFIRMED',
                'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE',
                'truck_id': None,
                'status': c.status
            })

        if not truck_starts:
            return jsonify({'error': 'No online trucks found. Open the driver app so it sends GPS data!'}), 400
            
        if not pending_customers:
            return jsonify({'error': 'No pending stops to recalculate.'}), 400
            
        # Filter out end depots from pending_customers so they aren't treated as mid-route stops
        real_pending_customers = [c for c in pending_customers if int(c['id']) > -1000 and c['confirmation'] != 'CANCELLED']
        
        cancelled_customers = [c for c in pending_customers if c['confirmation'] == 'CANCELLED']
        cancelled_by_truck = {}
        for c in cancelled_customers:
            tid = str(c['truck_id']) if c['truck_id'] else "1"
            if tid not in cancelled_by_truck: cancelled_by_truck[tid] = []
            cancelled_by_truck[tid].append(c)
        
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
        updates_by_route = {}
        # First, preserve completed stops for ALL active trucks
        for tid in active_truck_ids:
            route_key = f"route_{tid}"
            updates_by_route[route_key] = {}
            if route_key in routes_data and 'stops' in routes_data[route_key]:
                stops_raw = routes_data[route_key]['stops']
                stops_items = stops_raw.items() if isinstance(stops_raw, dict) else enumerate(stops_raw) if isinstance(stops_raw, list) else []
                for s_id, s_info in stops_items:
                    if s_info and s_info.get('status') != 'PENDING' and int(s_id) > -1000:
                        updates_by_route[route_key][str(s_id)] = s_info

        # Then apply the newly recalculated routes
        for idx, route in enumerate(new_routes):
            if idx < len(active_truck_ids):
                tid = active_truck_ids[idx]
                route_key = f"route_{tid}"
                
                # Determine starting sequence based on existing completed stops
                start_seq = 1 + len(updates_by_route[route_key])
                
                # We overwrite the remaining sequence for this truck
                for seq, cust_id in enumerate(route):
                    # We find the customer data
                    cust = next((c for c in real_pending_customers if c['id'] == str(cust_id) or c['id'] == cust_id), None)
                    if cust:
                        updates_by_route[route_key][str(cust_id)] = {
                            "name": cust['name'],
                            "address": cust['address'],
                            "phone": cust.get('phone', ''),
                            "lat": cust['lat'],
                            "lng": cust['lng'],
                            "sequence": start_seq + seq,
                            "status": "PENDING",
                            "confirmation": cust.get("confirmation", "NOT_CONFIRMED"),
                            "customer_status": cust.get("customer_status", "ACTIVE") or "ACTIVE"
                        }
                
                # Append cancelled customers
                if tid in cancelled_by_truck:
                    for c in cancelled_by_truck[tid]:
                        stop_num = len(updates_by_route[route_key])
                        updates_by_route[route_key][str(c['id'])] = {
                            "name": c['name'],
                            "address": c['address'],
                            "phone": c.get('phone', ''),
                            "lat": c['lat'],
                            "lng": c['lng'],
                            "sequence": stop_num + 1,
                            "status": c.get('status', 'PENDING'),
                            "confirmation": "CANCELLED",
                            "customer_status": getattr(c, "customer_status", "ACTIVE") if not isinstance(c, dict) else c.get("customer_status", "ACTIVE")
                        }
                
                # Re-append End Depot at the end of this truck's route
                depot_lat, depot_lng = end_coords[idx]
                updates_by_route[route_key][str(-1000 - idx)] = {
                    "name": "End Location / Depot",
                    "address": "Return to Depot",
                    "phone": "",
                    "lat": depot_lat,
                    "lng": depot_lng,
                    "sequence": start_seq + len(route),
                    "status": "PENDING",
                    "confirmation": "NOT_CONFIRMED"
                }
                        
        # Now PUT the new assignments individually to clear out old orphaned pending stops on these active routes
        for route_key, stops in updates_by_route.items():
            requests.put(f"{firebase_url}/routes/{route_key}/stops.json?auth={id_token}", json=stops)
        
        # Update SQL Database so Excel reports stay perfectly synced with live routes
        try:
            for idx, route in enumerate(new_routes):
                if idx < len(active_truck_ids):
                    tid = active_truck_ids[idx]
                    route_key = f"route_{tid}"
                    # Base sequence offsets for SQL
                    completed_count = len([s for s_id, s in updates_by_route[route_key].items() if s.get('status') != 'PENDING' and int(s_id) > -1000])
                    start_seq = completed_count + 1
                    
                    for seq, cust_id in enumerate(route):
                        sql_cust = db.session.get(Customer, int(cust_id))
                        if sql_cust:
                            sql_cust.truck_id = int(tid)
                            sql_cust.stop_number = start_seq + seq
            db.session.commit()
        except Exception as sql_e:
            print("Failed to update SQL assignments:", sql_e)
        
        recompute_route_metrics()
        return jsonify({'success': True, 'recalculated_stops': len(pending_customers)})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

