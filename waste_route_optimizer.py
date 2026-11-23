import os
import json
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
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
import datetime
import uuid
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS


_firebase_token_cache = {"token": None, "expires": 0}
def get_firebase_token():
    import time, requests
    global _firebase_token_cache
    if _firebase_token_cache["token"] and time.time() < _firebase_token_cache["expires"]:
        return _firebase_token_cache["token"]
        
    # Attempt 1: Authenticate with verified ADMIN role via Firebase Admin SDK
    admin_app = get_firebase_admin_app()
    if admin_app:
        try:
            from firebase_admin import auth as fb_auth
            token_bytes = fb_auth.create_custom_token(
                "server_admin",
                developer_claims={"role": "ADMIN", "admin_id": "0"},
                app=admin_app
            )
            custom_token = token_bytes.decode('utf-8') if isinstance(token_bytes, bytes) else token_bytes
            
            API_KEY = os.environ.get('FIREBASE_API_KEY', 'AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg')
            auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={API_KEY}"
            auth_res = requests.post(auth_url, json={"token": custom_token, "returnSecureToken": True}, timeout=6)
            if auth_res.status_code == 200:
                _firebase_token_cache["token"] = auth_res.json().get('idToken')
                _firebase_token_cache["expires"] = time.time() + 3000 # 50 minutes
                return _firebase_token_cache["token"]
            else:
                app.logger.warning(f"Failed to exchange admin custom token: {auth_res.status_code} {auth_res.text}")
        except Exception as e:
            app.logger.warning(f"Firebase Admin token minting failed in get_firebase_token: {e}")

    # Attempt 2: Fallback to anonymous auth only if Admin SDK credentials are not yet configured
    API_KEY = os.environ.get('FIREBASE_API_KEY', 'AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg')
    auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
    try:
        auth_res = requests.post(auth_url, json={"returnSecureToken": True}, timeout=6)
        if auth_res.status_code == 200:
            _firebase_token_cache["token"] = auth_res.json().get('idToken')
            _firebase_token_cache["expires"] = time.time() + 3000 # 50 minutes
            return _firebase_token_cache["token"]
    except Exception:
        pass
    return None

app = Flask(__name__)

@app.route('/healthz')
def healthz():
    return jsonify({'status': 'ok'}), 200

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'logo.jpg', mimetype='image/jpeg')

@app.errorhandler(Exception)
def handle_exception(e):
    try:
        db.session.rollback()
    except Exception:
        pass
    if isinstance(e, HTTPException):
        return e
    import traceback
    app.logger.error(f"Unhandled exception: {e}\n{traceback.format_exc()}")
    if app.debug or app.testing:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    return jsonify({'error': 'An internal server error occurred. Please contact the administrator.'}), 500



CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB upload limit

# Automatically use PostgreSQL if DATABASE_URL is set, otherwise detect persistent disk /var/data or fall back to local SQLite
database_url = os.environ.get('DATABASE_URL')
if not database_url and os.path.exists('/var/data'):
    database_url = 'sqlite:////var/data/routes.db'
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    elif database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///routes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,   # check a pooled connection is alive before using it; replace it if dead
    "pool_recycle": 280,     # recycle connections before Render's idle timeout closes them
}

db = SQLAlchemy(app)


app.secret_key = os.environ.get('SECRET_KEY', '7b4e2f91a5c84d3e0f6b2d1c9e8a7f4b3e2d1c0a9b8e7f6d5c4b3a2e1f0d9c8b')
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=bool(os.environ.get('RENDER') or os.environ.get('DATABASE_URL')),
    SESSION_COOKIE_SAMESITE='None' if (os.environ.get('RENDER') or os.environ.get('DATABASE_URL')) else 'Lax'
)

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "frame-ancestors 'self' capacitor://localhost http://localhost https://waste-route-optimizer-190z.onrender.com;"
    )
    return response

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
    generation_id = db.Column(db.String(36), nullable=True, index=True)
    assignment_revision = db.Column(db.BigInteger, nullable=False, default=0)
    email = db.Column(db.String(120), unique=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)
    auth_version = db.Column(db.Integer, default=1, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class UserPermission(db.Model):
    __tablename__ = 'user_permissions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    permission = db.Column(db.String(80), nullable=False, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (db.UniqueConstraint('user_id', 'permission', name='uq_user_permission'),)

class AdminAuditLog(db.Model):
    __tablename__ = 'admin_audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    acting_admin_id = db.Column(db.Integer, nullable=True, index=True)
    acting_username = db.Column(db.String(50), nullable=True)
    target_user_id = db.Column(db.Integer, nullable=True, index=True)
    target_username = db.Column(db.String(50), nullable=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)

class UrlCoordinateCache(db.Model):
    __tablename__ = 'url_coordinate_cache'
    url = db.Column(db.String(500), primary_key=True)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    location_url = db.Column(db.Text)
    google_maps_url = db.Column(db.Text)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    status = db.Column(db.String(50), default='PENDING', index=True)
    truck_id = db.Column(db.Integer, index=True)
    stop_number = db.Column(db.Integer)
    confirmation = db.Column(db.String(20), default='NOT_CONFIRMED')
    deliver_bag = db.Column(db.Boolean, default=False)
    customer_status = db.Column(db.String(20), default='ACTIVE')
    geocode_quality = db.Column(db.String(20), default='UNKNOWN')
    coord_source = db.Column(db.String(20), default='UNKNOWN')
    is_manually_corrected = db.Column(db.Boolean, default=False)
    master_customer_id = db.Column(db.Integer, nullable=True)

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
    is_assigned_instance = db.Column(db.Boolean, default=False, index=True)

class MasterCustomer(db.Model):
    __tablename__ = 'master_customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=False)
    location_url = db.Column(db.Text, nullable=True)
    google_maps_url = db.Column(db.Text, nullable=True)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    deliver_bag = db.Column(db.Boolean, default=False)
    customer_status = db.Column(db.String(20), default='ACTIVE', index=True)
    geocode_quality = db.Column(db.String(20), default='UNKNOWN')
    coord_source = db.Column(db.String(20), default='UNKNOWN')
    is_manually_corrected = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def to_dict(self, templates=None):
        maps_url = self.google_maps_url or self.location_url or ''
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone or '',
            'address': self.address or '',
            'location_url': maps_url,
            'google_maps_url': maps_url,
            'lat': self.lat,
            'lng': self.lng,
            'deliver_bag': bool(self.deliver_bag),
            'customer_status': self.customer_status or 'ACTIVE',
            'geocode_quality': self.geocode_quality or 'UNKNOWN',
            'coord_source': self.coord_source or 'UNKNOWN',
            'is_manually_corrected': bool(self.is_manually_corrected),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'templates': templates or []
        }

class AssignmentGlobalSequence(db.Model):
    __tablename__ = 'assignment_global_sequence'
    id = db.Column(db.Integer, primary_key=True)
    current_revision = db.Column(db.BigInteger, nullable=False, default=1)

class DriverLifecycleLedger(db.Model):
    __tablename__ = 'driver_lifecycle_ledger'
    generation_id = db.Column(db.String(36), primary_key=True)
    driver_id = db.Column(db.Integer, nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    deleted_at = db.Column(db.DateTime, nullable=True)
    last_revision = db.Column(db.BigInteger, nullable=False, default=0)

class AssignmentOutbox(db.Model):
    __tablename__ = 'assignment_outbox'
    id = db.Column(db.Integer, primary_key=True)
    op_id = db.Column(db.String(36), index=True, nullable=True)
    driver_id = db.Column(db.Integer, nullable=False, index=True)
    generation_id = db.Column(db.String(36), nullable=True, index=True)
    revision = db.Column(db.BigInteger, nullable=False, default=0, index=True)
    target_truck = db.Column(db.Integer, nullable=True)
    previous_truck = db.Column(db.Integer, nullable=True)
    mutation_type = db.Column(db.String(30), nullable=True)
    action = db.Column(db.String(20), nullable=True)
    affected_drivers_json = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='PREPARED', index=True)
    version = db.Column(db.Integer, default=1, nullable=False)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

class TruckTelemetryHistory(db.Model):
    __tablename__ = 'truck_telemetry_history'
    event_id = db.Column(db.String(64), primary_key=True)
    driver_id = db.Column(db.Integer, nullable=True, index=True)
    truck_id = db.Column(db.Integer, nullable=False, index=True)
    assignment_id = db.Column(db.String(64), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float, nullable=True)
    speed = db.Column(db.Float, nullable=True)
    bearing = db.Column(db.Float, nullable=True)
    provider = db.Column(db.String(32), nullable=True)
    capture_time = db.Column(db.BigInteger, nullable=False, index=True) # milliseconds
    sequence_number = db.Column(db.BigInteger, nullable=True)
    synced_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)

    def to_dict(self):
        return {
            'event_id': self.event_id,
            'driver_id': self.driver_id,
            'truck_id': self.truck_id,
            'assignment_id': self.assignment_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'accuracy': self.accuracy,
            'speed': self.speed,
            'bearing': self.bearing,
            'provider': self.provider,
            'capture_time': self.capture_time,
            'sequence_number': self.sequence_number,
            'synced_at': self.synced_at.strftime('%Y-%m-%d %H:%M:%S') if self.synced_at else None
        }

with app.app_context():
    db.create_all()
    
    from sqlalchemy import text
    try:
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_truck_id ON customers (truck_id);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_status ON customers (status);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_saved_templates_assigned ON saved_templates (is_assigned_instance);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_assignment_outbox_driver_id ON assignment_outbox (driver_id);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_assignment_outbox_status ON assignment_outbox (status);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_truck_telemetry_truck_capture ON truck_telemetry_history (truck_id, capture_time);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("CREATE TABLE IF NOT EXISTS assignment_global_sequence (id INTEGER PRIMARY KEY, current_revision BIGINT NOT NULL DEFAULT 1);"))
        db.session.execute(text("INSERT OR IGNORE INTO assignment_global_sequence (id, current_revision) VALUES (1, 1);"))
        # Align sequence current_revision to be strictly >= maximum of all existing table revisions
        try:
            db.session.execute(text("""
                UPDATE assignment_global_sequence 
                SET current_revision = MAX(
                    current_revision,
                    COALESCE((SELECT MAX(assignment_revision) FROM users), 1),
                    COALESCE((SELECT MAX(revision) FROM assignment_outbox), 1),
                    COALESCE((SELECT MAX(last_revision) FROM driver_lifecycle_ledger), 1)
                )
                WHERE id = 1;
            """))
        except Exception:
            pass
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("CREATE TABLE IF NOT EXISTS driver_lifecycle_ledger (generation_id VARCHAR(36) PRIMARY KEY, driver_id INTEGER NOT NULL, is_active BOOLEAN NOT NULL DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, deleted_at TIMESTAMP NULL, last_revision BIGINT NOT NULL DEFAULT 0);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_lifecycle_driver_id ON driver_lifecycle_ledger (driver_id);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN generation_id VARCHAR(36);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN assignment_revision BIGINT DEFAULT 0;"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE assignment_outbox ADD COLUMN generation_id VARCHAR(36);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE assignment_outbox ADD COLUMN revision BIGINT DEFAULT 0;"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE assignment_outbox ADD COLUMN action VARCHAR(20);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_assignment_outbox_driver_rev ON assignment_outbox (driver_id, revision);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_assignment_outbox_generation ON assignment_outbox (generation_id);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        # Backfill any existing driver without generation_id
        import uuid as _uuid
        drivers_to_init = User.query.filter_by(role='DRIVER').filter((User.generation_id == None) | (User.generation_id == '')).all()
        for _d in drivers_to_init:
            _gid = _uuid.uuid4().hex
            _d.generation_id = _gid
            _d.assignment_revision = max(_d.assignment_revision or 0, 1)
            _led = DriverLifecycleLedger.query.filter_by(generation_id=_gid).first()
            if not _led:
                db.session.add(DriverLifecycleLedger(
                    generation_id=_gid,
                    driver_id=_d.id,
                    is_active=True,
                    last_revision=_d.assignment_revision
                ))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE assignment_outbox ADD COLUMN op_id VARCHAR(36);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE assignment_outbox ADD COLUMN previous_truck INTEGER;"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE assignment_outbox ADD COLUMN mutation_type VARCHAR(30);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE assignment_outbox ADD COLUMN affected_drivers_json TEXT;"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE assignment_outbox ADD COLUMN version INTEGER DEFAULT 1;"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_assignment_outbox_op_id ON assignment_outbox (op_id);"))
        db.session.commit()
    except Exception:
        db.session.rollback()
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
        db.session.execute(text("ALTER TABLE customers ADD COLUMN deliver_bag BOOLEAN DEFAULT FALSE;"))
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
        db.session.execute(text("ALTER TABLE customers ADD COLUMN geocode_quality VARCHAR(20) DEFAULT 'UNKNOWN';"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN coord_source VARCHAR(20) DEFAULT 'UNKNOWN';"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN is_manually_corrected BOOLEAN DEFAULT FALSE;"))
        db.session.commit()
    except:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE customers ADD COLUMN is_manually_corrected BOOLEAN DEFAULT 0;"))
            db.session.commit()
        except:
            db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN master_customer_id INTEGER;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS master_customers (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                address TEXT NOT NULL,
                location_url TEXT,
                google_maps_url TEXT,
                lat FLOAT,
                lng FLOAT,
                deliver_bag BOOLEAN DEFAULT 0,
                customer_status VARCHAR(20) DEFAULT 'ACTIVE',
                geocode_quality VARCHAR(20) DEFAULT 'UNKNOWN',
                coord_source VARCHAR(20) DEFAULT 'UNKNOWN',
                is_manually_corrected BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_master_customers_status ON master_customers (customer_status);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_master_customers_name ON master_customers (name);"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE master_customers ADD COLUMN google_maps_url TEXT;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("UPDATE master_customers SET google_maps_url = location_url WHERE google_maps_url IS NULL AND location_url IS NOT NULL;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE customers ADD COLUMN google_maps_url TEXT;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("UPDATE customers SET google_maps_url = location_url WHERE google_maps_url IS NULL AND location_url IS NOT NULL;"))
        db.session.commit()
    except:
        db.session.rollback()

    # User management & granular permissions migrations
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(120);"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN is_superadmin BOOLEAN DEFAULT 0;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN auth_version INTEGER DEFAULT 1;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN last_login TIMESTAMP;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN created_at TIMESTAMP;"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email) WHERE email IS NOT NULL AND email != '';"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                permission VARCHAR(80) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE (user_id, permission)
            );
        """))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_user_permissions_user_id ON user_permissions (user_id);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_user_permissions_perm ON user_permissions (permission);"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acting_admin_id INTEGER,
                acting_username VARCHAR(50),
                target_user_id INTEGER,
                target_username VARCHAR(50),
                action VARCHAR(80) NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_acting_admin ON admin_audit_logs (acting_admin_id);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_target_user ON admin_audit_logs (target_user_id);"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_action ON admin_audit_logs (action);"))
        db.session.commit()
    except:
        db.session.rollback()

    # Re-evaluate existing centroid and default rows to FAILED (clearing lat/lng so they are not plotted as real coordinates)
    try:
        db.session.execute(text("""
            UPDATE customers
            SET geocode_quality = 'FAILED', lat = NULL, lng = NULL, coord_source = 'FAILED'
            WHERE (
                (abs(lat - 23.0145) < 0.003 AND abs(lng - 72.5918) < 0.003)
                OR (abs(lat - 23.0225) < 0.001 AND abs(lng - 72.5714) < 0.001)
            ) AND (is_manually_corrected IS NULL OR is_manually_corrected = FALSE);
        """))
        db.session.commit()
    except Exception as mig_e:
        db.session.rollback()

    # Specifically correct Prajapati Kirankumar / Kumud Nagar Society in customers table if present
    try:
        for c in Customer.query.filter(
            (Customer.address.like('%KUMUD NAGAR%')) | (Customer.phone.like('%9687430655%'))
        ).all():
            c.lat = 23.0744137
            c.lng = 72.5280572
            c.coord_source = 'FILE'
            c.geocode_quality = 'EXACT'
            c.is_manually_corrected = True
        db.session.commit()
    except Exception as cust_e:
        db.session.rollback()

    # Sanitize saved_templates customers_json: fix Kumud Nagar coords and clear uncorrected centroids
    try:
        for tmpl in SavedTemplate.query.all():
            if not tmpl.customers_json:
                continue
            c_list = json.loads(tmpl.customers_json or '[]')
            modified = False
            for c_item in c_list:
                c_addr = str(c_item.get('address') or '')
                c_phone = str(c_item.get('phone') or '')
                clat = c_item.get('lat')
                clng = c_item.get('lng')

                if 'KUMUD NAGAR' in c_addr.upper() or '9687430655' in c_phone:
                    if clat != 23.0744137 or clng != 72.5280572:
                        c_item['lat'] = 23.0744137
                        c_item['lng'] = 72.5280572
                        c_item['coord_source'] = 'FILE'
                        c_item['geocode_quality'] = 'EXACT'
                        c_item['is_manually_corrected'] = True
                        modified = True
                elif clat is not None and clng is not None and not c_item.get('is_manually_corrected'):
                    if (abs(clat - 23.0145) < 0.003 and abs(clng - 72.5918) < 0.003) or                        (abs(clat - 23.0225) < 0.001 and abs(clng - 72.5714) < 0.001):
                        c_item['lat'] = None
                        c_item['lng'] = None
                        c_item['geocode_quality'] = 'FAILED'
                        c_item['coord_source'] = 'FAILED'
                        modified = True
            if modified:
                tmpl.customers_json = json.dumps(c_list)
        db.session.commit()
    except Exception as tmpl_e:
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
    admin_env_pass = os.environ.get('ADMIN_PASSWORD')
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        init_pass = admin_env_pass or 'green@2026'
        db.session.add(User(username='admin', password_hash=generate_password_hash(init_pass), role='ADMIN', is_active=True, is_superadmin=True, email='admin@trashtrekyx.com', name='Primary Admin'))
        db.session.commit()
    else:
        if admin_env_pass:
            admin_user.password_hash = generate_password_hash(admin_env_pass)
        if not getattr(admin_user, 'is_superadmin', False) or not getattr(admin_user, 'is_active', True):
            admin_user.is_superadmin = True
            admin_user.is_active = True
        if not getattr(admin_user, 'email', None):
            admin_user.email = 'admin@trashtrekyx.com'
        if not getattr(admin_user, 'name', None):
            admin_user.name = 'Primary Admin'
        db.session.commit()

    # One-time seed of saved master templates from bundled instance/routes.db onto fresh persistent disk
    try:
        seeded_flag = Metadata.query.filter_by(key='initial_templates_seeded').first()
        if not seeded_flag:
            if SavedTemplate.query.count() == 0:
                seed_db_path = os.path.join(app.root_path, 'instance', 'routes.db')
                if os.path.exists(seed_db_path):
                    import sqlite3
                    sconn = sqlite3.connect(seed_db_path)
                    scur = sconn.cursor()
                    rows = scur.execute("SELECT name, metadata_json, customers_json, is_assigned_instance FROM saved_templates WHERE COALESCE(is_assigned_instance, 0) = 0").fetchall()
                    sconn.close()
                    for r_name, r_meta, r_custs, r_is_ass in rows:
                        db.session.add(SavedTemplate(
                            name=r_name,
                            metadata_json=r_meta,
                            customers_json=r_custs,
                            is_assigned_instance=False
                        ))
            db.session.add(Metadata(key='initial_templates_seeded', value='true'))
            db.session.commit()
    except Exception as seed_e:
        print("One-time template seed error:", seed_e)
        db.session.rollback()

import urllib.parse

def validate_customer_name(name):
    """
    Mandatory. Reject empty or whitespace-only values. Trim spaces.
    """
    if name is None:
        return False, "Customer Name is required."
    clean = str(name).strip()
    if not clean:
        return False, "Customer Name cannot be empty or whitespace only."
    return True, clean

def validate_customer_address(address):
    """
    Mandatory. Reject empty or whitespace-only values. Preserve full address.
    """
    if address is None:
        return False, "Address is required."
    clean = str(address).strip()
    if not clean:
        return False, "Address cannot be empty or whitespace only."
    return True, clean

def validate_phone_number(phone):
    """
    Mandatory. Support Indian phone numbers and reasonable international formats.
    Support country codes (+91, 91, +1, etc.), spaces, dashes, parentheses.
    Reject letters, empty values, or invalid digit counts (must have 7 to 15 digits).
    """
    if phone is None:
        return False, "Phone Number is required."
    phone_str = str(phone).strip()
    if not phone_str:
        return False, "Phone Number is required."
    if phone_str.endswith('.0'):
        phone_str = phone_str[:-2].strip()
    if re.search(r'[a-zA-Z]', phone_str):
        return False, "Phone number contains invalid alphabetic characters."
    if not re.match(r'^\+?[0-9\s\-\.\(\)]{7,25}$', phone_str):
        return False, "Invalid phone number format."
    digits = re.sub(r'\D', '', phone_str)
    if len(digits) < 7:
        return False, "Phone number is too short (minimum 7 digits required)."
    if len(digits) > 15:
        return False, "Phone number is too long (maximum 15 digits allowed)."
    return True, phone_str

def validate_google_maps_url(url):
    """
    Mandatory. Validate that URL uses HTTPS and a recognized Google Maps domain
    or supported Google Maps short-link domain (maps.google.*, google.*/maps,
    maps.app.goo.gl, goo.gl/maps). Reject unrelated websites and malformed URLs.
    """
    if url is None:
        return False, "Google Maps Location URL is required."
    url_str = str(url).strip()
    if not url_str:
        return False, "Google Maps Location URL is required."
    if not url_str.lower().startswith('https://'):
        return False, "Google Maps URL must use HTTPS (e.g. https://maps.google.com/...)."
    try:
        parsed = urllib.parse.urlparse(url_str)
    except Exception:
        return False, "Malformed Google Maps URL."
    if parsed.scheme.lower() != 'https':
        return False, "Google Maps URL must use HTTPS."
    netloc = (parsed.netloc or '').lower()
    if ':' in netloc:
        netloc = netloc.split(':')[0]
    if not netloc:
        return False, "Google Maps URL must contain a valid host domain."

    # Supported short links
    if netloc == 'maps.app.goo.gl':
        if len(parsed.path) > 1:
            return True, url_str
        return False, "Google Maps share link is missing location path."
    if netloc == 'goo.gl':
        if parsed.path.startswith('/maps') or len(parsed.path) > 1:
            return True, url_str
        return False, "Invalid goo.gl Maps link."

    # Google Maps subdomains: maps.google.* (e.g. maps.google.com, maps.google.co.in)
    is_maps_google = bool(re.match(r'^(?:[a-z0-9\-]+\.)*maps\.google\.[a-z\.]+$', netloc) or netloc == 'maps.google.com')
    # Main Google domains: (www.)google.*/maps or /search?*
    is_google_domain = bool(re.match(r'^(?:www\.)?google\.[a-z\.]+$', netloc))

    if is_maps_google:
        return True, url_str
    elif is_google_domain and (parsed.path.startswith('/maps') or (parsed.path.startswith('/search') and 'q=' in parsed.query)):
        return True, url_str
    else:
        return False, "URL must be a valid Google Maps link (e.g. https://maps.google.com/... or https://maps.app.goo.gl/...)."

def validate_coordinates(lat, lng):
    """
    Optional coordinates validation.
    If provided: lat must be between -90 and 90, lng between -180 and 180.
    """
    lat_f = None
    lng_f = None
    if lat is not None and str(lat).strip() != '':
        try:
            lat_f = float(str(lat).strip())
            if not (-90.0 <= lat_f <= 90.0):
                return False, None, None, "Latitude must be a valid number between -90 and 90."
        except (ValueError, TypeError):
            return False, None, None, "Invalid numeric latitude value."

    if lng is not None and str(lng).strip() != '':
        try:
            lng_f = float(str(lng).strip())
            if not (-180.0 <= lng_f <= 180.0):
                return False, None, None, "Longitude must be a valid number between -180 and 180."
        except (ValueError, TypeError):
            return False, None, None, "Invalid numeric longitude value."

    return True, lat_f, lng_f, None

def extract_coords_from_gmaps_url_fast(url):
    """
    Fast sub-millisecond regex extraction of coordinates from Google Maps URLs.
    """
    if not url or not isinstance(url, str):
        return None, None
    u = url.strip()
    pin = re.search(r'!3d(-?\d+(?:\.\d+)?)\!4d(-?\d+(?:\.\d+)?)', u)
    if pin:
        try:
            clat, clng = float(pin.group(1)), float(pin.group(2))
            if (-90.0 <= clat <= 90.0) and (-180.0 <= clng <= 180.0):
                return clat, clng
        except (ValueError, TypeError):
            pass
    q = re.search(r'[?&]q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', u)
    if q:
        try:
            clat, clng = float(q.group(1)), float(q.group(2))
            if (-90.0 <= clat <= 90.0) and (-180.0 <= clng <= 180.0):
                return clat, clng
        except (ValueError, TypeError):
            pass
    vp = re.search(r'@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', u)
    if vp:
        try:
            clat, clng = float(vp.group(1)), float(vp.group(2))
            if (-90.0 <= clat <= 90.0) and (-180.0 <= clng <= 180.0):
                return clat, clng
        except (ValueError, TypeError):
            pass
    ll = re.search(r'[?&]ll=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', u)
    if ll:
        try:
            clat, clng = float(ll.group(1)), float(ll.group(2))
            if (-90.0 <= clat <= 90.0) and (-180.0 <= clng <= 180.0):
                return clat, clng
        except (ValueError, TypeError):
            pass
    return None, None

def normalize_phone_for_dedup(phone):
    if not phone:
        return ''
    digits = re.sub(r'\D', '', str(phone).strip())
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits if len(digits) >= 7 else ''

def normalize_address_for_dedup(address):
    if not address:
        return ''
    addr = str(address).strip().lower()
    addr = re.sub(r'[\,\.\-\/\#]', ' ', addr)
    addr = re.sub(r'\s+', ' ', addr).strip()
    return addr

def _save_url_coordinate_cache(url, lat, lng):
    try:
        with app.app_context():
            entry = UrlCoordinateCache(url=url, lat=lat, lng=lng)
            db.session.merge(entry)
            db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

def resolve_gmaps_url(url):
    if not url or not isinstance(url, str):
        return None, None
    url = url.strip()

    # 1. Fast local coordinate extraction if URL string itself contains coordinates
    pin_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if pin_match:
        clat, clng = float(pin_match.group(1)), float(pin_match.group(2))
        if (8 <= clat <= 38) and (68 <= clng <= 98):
            _save_url_coordinate_cache(url, clat, clng)
            return clat, clng
    q_match = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if q_match:
        clat, clng = float(q_match.group(1)), float(q_match.group(2))
        if (8 <= clat <= 38) and (68 <= clng <= 98):
            _save_url_coordinate_cache(url, clat, clng)
            return clat, clng
    vp_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if vp_match:
        clat, clng = float(vp_match.group(1)), float(vp_match.group(2))
        if (8 <= clat <= 38) and (68 <= clng <= 98):
            _save_url_coordinate_cache(url, clat, clng)
            return clat, clng
    c_lat, c_lng = extract_lat_lng(url)
    if c_lat and c_lng and (8 <= c_lat <= 38) and (68 <= c_lng <= 98):
        _save_url_coordinate_cache(url, c_lat, c_lng)
        return c_lat, c_lng

    # 2. Check Database URL cache (persisted keyed by URL, resolved once)
    try:
        with app.app_context():
            cached = db.session.get(UrlCoordinateCache, url)
            if cached and cached.lat and cached.lng:
                return cached.lat, cached.lng
    except Exception:
        pass

    # 3. Network resolution with retry and backoff (timeout=6s, 3 attempts)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    for attempt in range(3):
        try:
            res = requests.get(url, allow_redirects=True, headers=headers, timeout=6.0)
            target_url = res.url or ''
            
            lat, lng = None, None
            pin_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', target_url)
            if pin_match: lat, lng = float(pin_match.group(1)), float(pin_match.group(2))
            
            if not lat or not lng:
                q_match = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', target_url)
                if q_match: lat, lng = float(q_match.group(1)), float(q_match.group(2))
                
            if not lat or not lng:
                vp_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', target_url)
                if vp_match: lat, lng = float(vp_match.group(1)), float(vp_match.group(2))

            # Preview link parsing if direct coords not present in redirect URL
            if (not lat or not lng) and res.text:
                preview_match = re.search(r'href="(/maps/preview/place[^"]+)"', res.text)
                if preview_match:
                    import html
                    preview_url = "https://www.google.com" + html.unescape(preview_match.group(1))
                    p_res = requests.get(preview_url, headers=headers, timeout=6.0)
                    coord_match = re.search(r'\[null,\s*null,\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\]', p_res.text)
                    if coord_match:
                        lat, lng = float(coord_match.group(1)), float(coord_match.group(2))

            # Coordinates extracted from response text (e.g. meta tags)
            if (not lat or not lng) and res.text:
                meta_match = re.search(r'itemprop="image"\s+content="[^"]*\?center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', res.text)
                if meta_match:
                    lat, lng = float(meta_match.group(1)), float(meta_match.group(2))

            if lat and lng and (8 <= lat <= 38) and (68 <= lng <= 98):
                _save_url_coordinate_cache(url, lat, lng)
                return lat, lng

            # Place name fallback
            import urllib.parse
            unquoted_url = urllib.parse.unquote_plus(target_url)
            place_match = re.search(r'place/([^/]+)/', unquoted_url)
            if place_match:
                place_name = place_match.group(1).replace('+', ' ').strip()
                return None, place_name

            break # No valid coords found, no need to retry network
        except Exception as e:
            if attempt < 2:
                time.sleep(1.0 * (2 ** attempt))
            else:
                print(f"[GMAPS RESOLVE ERROR] Failed to resolve location link after 3 attempts: {url}. Error: {e}")

    # Never cache failed (None, None) so future attempts or manual corrections can succeed
    return None, None

def clean_address_for_geocoding(addr):
    if not addr or not isinstance(addr, str):
        return ''
    s = re.sub(r'[\r\n\t]+', ' ', addr.strip())
    pin_match = re.search(r'\b(38\d{4})\b', s)
    pincode = pin_match.group(1) if pin_match else None
    
    # Strip leading flat/block/house/plot/shop/office numbers (e.g. '1760,', 'F /54,', 'B/303,')
    s = re.sub(r'^\s*(?:flat|block|house|plot|shop|office|room|survey)?\s*[a-z0-9/-]+\s*,\s*', '', s, flags=re.I)
    
    # Strip landmark clauses: 'b/h gota uhc', 'opp revati tower', 'nr. iscon cross road'
    s = re.sub(r'\b(?:b/h|behind|opp|opposite|nr\.?|near|next\s+to|beside)\s+[^,]+,?', '', s, flags=re.I)
    
    # Fix typo 'ARE' -> 'Area'
    s = re.sub(r'\bARE\b', 'Area', s, flags=re.I)
    
    # Clean up commas and spaces
    s = re.sub(r'\s*,\s*', ', ', s)
    s = re.sub(r',\s*,+', ', ', s)
    s = re.sub(r'\s+', ' ', s).strip(' ,')
    
    # Append city context if missing
    if 'ahmedabad' not in s.lower() and 'gujarat' not in s.lower():
        suffix = f', Ahmedabad, Gujarat {pincode}, India' if pincode else ', Ahmedabad, Gujarat, India'
        s += suffix
    elif pincode and pincode not in s:
        s += f' {pincode}'
    return s.strip()

def geocode_address_robust(addr):
    if not addr or not isinstance(addr, str) or not addr.strip():
        return None, None, 'FAILED'
        
    cleaned = clean_address_for_geocoding(addr)
    
    # 1. Optional Google Maps API (if GMAPS_API_KEY is set)
    gkey = os.environ.get('GMAPS_API_KEY')
    if gkey:
        try:
            import requests
            params = {
                'address': cleaned,
                'key': gkey,
                'components': 'country:IN',
                'bounds': '22.85,72.40|23.20,72.80'
            }
            res = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params, timeout=5).json()
            if res.get('status') == 'OK' and res.get('results'):
                first = res['results'][0]
                loc = first['geometry']['location']
                glat, glng = loc['lat'], loc['lng']
                loc_type = first['geometry'].get('location_type', 'APPROXIMATE')
                types = first.get('types', [])
                # Reject country, state, city, and locality broad results
                if not any(t in types for t in ['country', 'administrative_area_level_1', 'administrative_area_level_2', 'locality']):
                    if 22.85 <= glat <= 23.20 and 72.40 <= glng <= 72.80:
                        qual = 'EXACT' if loc_type == 'ROOFTOP' else 'APPROXIMATE'
                        return glat, glng, qual
        except Exception as ge:
            print(f"Google Geocode error: {ge}")

    # 2. ArcGIS with strict point/street validation and centroid rejection
    try:
        from geopy.geocoders import ArcGIS
        arc = ArcGIS()
        queries = [cleaned]
        raw_ahmedabad = addr.strip() + ', Ahmedabad, Gujarat, India' if 'ahmedabad' not in addr.lower() else addr.strip()
        if raw_ahmedabad not in queries:
            queries.append(raw_ahmedabad)
            
        parts = [p.strip() for p in cleaned.split(',') if p.strip()]
        for k in [4, 3]:
            if len(parts) > k:
                sub_q = ", ".join(parts[-k:])
                if sub_q not in queries:
                    queries.append(sub_q)
                    
        for q in queries:
            try:
                loc = arc.geocode(q, timeout=5)
                if loc:
                    clat, clng = loc.latitude, loc.longitude
                    raw = loc.raw or {}
                    score = raw.get('score', 0)
                    addr_type = raw.get('attributes', {}).get('Addr_type', '')
                    matched_addr = loc.address.strip() if hasattr(loc, 'address') and loc.address else ''
                    
                    # Treat city, locality, and administrative level results as FAILED
                    if matched_addr in ['Ahmedabad, Gujarat', 'Ahmedabad', 'Ahmedabad, India'] or addr_type in ['City', 'Locality', 'Admin', 'Region', 'Country']:
                        continue
                    if abs(clat - 23.0145) < 0.003 and abs(clng - 72.5918) < 0.003:
                        continue
                    if abs(clat - 23.0225) < 0.001 and abs(clng - 72.5714) < 0.001:
                        continue
                        
                    # Validate within Ahmedabad metro bounds
                    if 22.85 <= clat <= 23.20 and 72.40 <= clng <= 72.80:
                        # Strict EXACT rule: only high-score PointAddress is EXACT
                        if score >= 90 and (addr_type == 'PointAddress' or 'point' in addr_type.lower()):
                            return clat, clng, 'EXACT'
                        elif score >= 80:
                            return clat, clng, 'APPROXIMATE'
            except Exception:
                pass
    except Exception as ae:
        print(f"ArcGIS Geocode error: {ae}")

    return None, None, 'FAILED'

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
    loc_url_col = next((c for c in cols if ('location' in c or 'map' in c or 'link' in c or 'url' in c) and c != coord_col and c != lat_col and c != lng_col), None)
    if not loc_url_col:
        for c in cols:
            first_val = str(df[c].dropna().head(1).iloc[0]) if len(df[c].dropna()) else ""
            if 'http' in first_val or 'maps.app' in first_val or 'goo.gl' in first_val:
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
        coord_source = 'UNKNOWN'
        geocode_quality = 'UNKNOWN'
        
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
                        coord_source = 'MAPS_LINK'
                        geocode_quality = 'EXACT'
                
        if lat is None or lng is None:
            if coord_col: lat, lng = extract_lat_lng(row[coord_col])
            elif lat_col and lng_col: lat, lng = row[lat_col], row[lng_col]
            if lat is not None and lng is not None:
                coord_source = 'FILE'
                geocode_quality = 'EXACT'
                
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
                glat, glng, gqual = geocode_address_robust(str(address))
                if glat is not None and glng is not None:
                    lat, lng = glat, glng
                    geocode_quality = gqual
                    coord_source = 'GEOCODE'
                else:
                    geocode_quality = 'FAILED'
                    coord_source = 'FAILED'
            else:
                geocode_quality = 'FAILED'
                coord_source = 'FAILED'
            
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

            # Never drop stops missing coordinates: preserve them with None coordinates and FAILED quality
            cust_lat = float(lat) if (lat is not None and not pd.isna(lat)) else None
            cust_lng = float(lng) if (lng is not None and not pd.isna(lng)) else None

            customers.append({
                'id': sr_id,
                'name': row.get(name_col) if name_col and not pd.isna(row.get(name_col)) else f"Customer {idx+1}",
                'phone': phone_val,
                'address': row.get(address_col) if address_col and not pd.isna(row.get(address_col)) else "",
                'location_url': loc_url_clean,
                'google_maps_url': loc_url_clean,
                'lat': cust_lat,
                'lng': cust_lng,
                'status': 'PENDING',
                'customer_status': 'ACTIVE',
                'geocode_quality': geocode_quality,
                'coord_source': coord_source,
                'is_manually_corrected': False
            })
        except Exception as add_e:
            print("Error appending customer in read_data_file:", add_e)

    # Cluster check: Only downgrade 3+ identical coordinates if derived from address GEOCODE or DEFAULT fallback
    # Multi-customer apartments whose coordinates came from FILE or MAPS_LINK must stay EXACT!
    try:
        coord_clusters = {}
        for c in customers:
            if c.get('lat') is not None and c.get('lng') is not None:
                pt_key = (round(c['lat'], 5), round(c['lng'], 5))
                coord_clusters.setdefault(pt_key, []).append(c)

        for pt_key, group in coord_clusters.items():
            if len(group) >= 3:
                for c in group:
                    if c.get('coord_source') in ('GEOCODE', 'DEFAULT'):
                        c['geocode_quality'] = 'APPROXIMATE'
    except Exception as ce:
        print("Error evaluating coordinate clusters in read_data_file:", ce)

    # F1: Outlier detection & safe conditional auto-swap (flag-only, no dropping)
    try:
        import statistics
        from geopy.distance import geodesic
        valid_pts = [(c['lat'], c['lng']) for c in customers if c.get('lat') is not None and c.get('lng') is not None and 8.0 <= c['lat'] <= 38.0 and 68.0 <= c['lng'] <= 98.0]
        if valid_pts:
            med_lat = statistics.median([p[0] for p in valid_pts])
            med_lng = statistics.median([p[1] for p in valid_pts])
            med_center = (med_lat, med_lng)
            
            for c in customers:
                clat, clng = c.get('lat'), c.get('lng')
                if clat is None or clng is None:
                    c['is_outlier'] = True
                    c['outlier_warning'] = 'Missing coordinates'
                    continue
                
                in_india = (8.0 <= clat <= 38.0) and (68.0 <= clng <= 98.0)
                # Auto-swap ONLY if swapped point is in India AND within 60 km of median
                swapped_lat, swapped_lng = clng, clat
                if (not in_india) and (8.0 <= swapped_lat <= 38.0 and 68.0 <= swapped_lng <= 98.0):
                    swapped_dist = geodesic(med_center, (swapped_lat, swapped_lng)).kilometers
                    if swapped_dist <= 60.0:
                        print(f"[AUTO-SWAP] Corrected inverted coordinates for stop {c['id']} ({c['name']}): ({clat}, {clng}) -> ({swapped_lat}, {swapped_lng}) [{swapped_dist:.1f} km from median]")
                        c['lat'] = swapped_lat
                        c['lng'] = swapped_lng
                        clat, clng = swapped_lat, swapped_lng
                        in_india = True

                dist_km = geodesic(med_center, (clat, clng)).kilometers
                if (not in_india) or dist_km > 60.0:
                    c['is_outlier'] = True
                    c['outlier_distance_km'] = round(dist_km, 1)
                    c['outlier_warning'] = f"Stop is {dist_km:.1f} km from fleet center (limit: 60 km)" if in_india else f"Stop ({clat}, {clng}) is outside India"
                    print(f"[OUTLIER DETECTED] Stop {c['id']} ({c['name']}): {c['outlier_warning']}")
    except Exception as e:
        print("Error during outlier detection in read_data_file:", e)
            
    return customers

from functools import wraps
from flask import session, redirect, url_for, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

def get_auth_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt='tt-auth-token-v1')

def get_token_fingerprint(user):
    """Derive token fingerprint from SHA-256 of password hash so password reset instantly invalidates old tokens."""
    import hashlib
    return hashlib.sha256((user.password_hash or '').encode('utf-8')).hexdigest()[:16]

def generate_auth_token(user):
    """
    Generates a cryptographically signed, timestamped, tamper-proof auth token.
    Contains user identity and session fingerprint.
    """
    s = get_auth_serializer()
    return s.dumps({
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'fp': get_token_fingerprint(user)
    })

def verify_auth_token(token_str, max_age=86400):
    """
    Cryptographically verifies an authentication token.
    
    STRICT PRODUCTION SECURITY RULES:
    1. Unconditionally rejects raw numeric IDs or pure digit strings (predictable IDs can NEVER authenticate).
    2. Validates HMAC cryptographic signature and ensures token is within validity window (default 24h).
    3. Re-queries the live user record from the database to ensure user exists and is active.
    4. Compares session fingerprint with live password hash - automatically invalidates tokens if password changed.
    5. Checks live role - sensitive authorization decisions always use current database state.
    """
    if not token_str:
        return None
    token_str = str(token_str).strip()
    
    # Strictly reject raw integer IDs and pure digit strings
    if token_str.isdigit():
        return None

    # Cryptographically verify signed token
    s = get_auth_serializer()
    try:
        data = s.loads(token_str, max_age=max_age)
        uid = data.get('user_id')
        if not uid:
            return None
        
        # Fresh query from database - never rely on stale token payload
        user = db.session.get(User, int(uid))
        if not user:
            return None

        # Check session fingerprint: if password changed, token is revoked
        if data.get('fp') != get_token_fingerprint(user):
            return None

        # Verify current server-side role matches token claim
        if user.role != data.get('role'):
            return None

        return user
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None

_firebase_admin_app = None
_firebase_admin_diagnostic = {
    "status": "uninitialized",
    "stage": "not_started",
    "env_var_present": False,
    "env_var_length": 0,
    "env_var_trimmed_length": 0,
    "first_char_repr": None,
    "last_char_repr": None,
    "starts_with_brace": False,
    "ends_with_brace": False,
    "has_begin_private_key": False,
    "has_end_private_key": False,
    "looks_like_assignment": False,
    "newline_count": 0,
    "is_file_path": False,
    "file_path_exists": False,
    "json_parsed": False,
    "has_type": False,
    "type_value": None,
    "project_id_match": False,
    "project_id_found": None,
    "has_client_email": False,
    "has_private_key": False,
    "private_key_length": 0,
    "cert_created": False,
    "app_initialized": False,
    "error_class": None,
    "error_message": None
}

def get_firebase_admin_diagnostic():
    global _firebase_admin_diagnostic
    return dict(_firebase_admin_diagnostic)

def get_firebase_admin_app():
    global _firebase_admin_app, _firebase_admin_diagnostic
    if _firebase_admin_app is not None:
        _firebase_admin_diagnostic["status"] = "initialized"
        _firebase_admin_diagnostic["app_initialized"] = True
        return _firebase_admin_app
        
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as e:
        _firebase_admin_diagnostic["status"] = "failed"
        _firebase_admin_diagnostic["stage"] = "import_failed"
        _firebase_admin_diagnostic["error_class"] = type(e).__name__
        _firebase_admin_diagnostic["error_message"] = "firebase_admin package not installed"
        app.logger.warning("firebase_admin package not installed")
        return None
        
    if firebase_admin._apps:
        _firebase_admin_app = firebase_admin.get_app()
        _firebase_admin_diagnostic["status"] = "initialized"
        _firebase_admin_diagnostic["stage"] = "already_initialized"
        _firebase_admin_diagnostic["app_initialized"] = True
        return _firebase_admin_app
        
    is_prod = bool(os.environ.get('RENDER') or os.environ.get('DATABASE_URL') or os.environ.get('FLASK_ENV') == 'production' or os.environ.get('ENV') == 'production')
    raw_cred = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    _firebase_admin_diagnostic["stage"] = "checking_env_var"
    _firebase_admin_diagnostic["env_var_present"] = bool(raw_cred and raw_cred.strip())
    _firebase_admin_diagnostic["env_var_length"] = len(raw_cred) if raw_cred else 0
    
    if raw_cred and raw_cred.strip():
        s = raw_cred.strip()
        _firebase_admin_diagnostic["env_var_trimmed_length"] = len(s)
        _firebase_admin_diagnostic["first_char_repr"] = repr(s[0]) if s else None
        _firebase_admin_diagnostic["last_char_repr"] = repr(s[-1]) if s else None
        _firebase_admin_diagnostic["starts_with_brace"] = s.startswith('{')
        _firebase_admin_diagnostic["ends_with_brace"] = s.endswith('}')
        _firebase_admin_diagnostic["has_begin_private_key"] = ('BEGIN PRIVATE KEY' in s)
        _firebase_admin_diagnostic["has_end_private_key"] = ('END PRIVATE KEY' in s)
        _firebase_admin_diagnostic["newline_count"] = s.count('\n')
        
        # Check if user entered key assignment e.g. FIREBASE_SERVICE_ACCOUNT_JSON={...} or export ...
        if s.startswith('export '):
            s = s[7:].strip()
        if '=' in s[:45]:
            _firebase_admin_diagnostic["looks_like_assignment"] = True
            parts = s.split('=', 1)
            candidate = parts[1].strip()
            if candidate.startswith(('{', "'", '"', '/')):
                s = candidate

        # Check if user entered a file path instead of raw JSON
        if s.endswith('.json') or os.path.exists(s) or s.startswith('/etc/secrets/') or (len(s) > 1 and s[1] == ':'):
            _firebase_admin_diagnostic["is_file_path"] = True
            _firebase_admin_diagnostic["file_path_exists"] = os.path.exists(s)
            if os.path.exists(s):
                try:
                    with open(s, 'r', encoding='utf-8') as f:
                        s = f.read().strip()
                except Exception as fe:
                    _firebase_admin_diagnostic["error_class"] = type(fe).__name__
                    _firebase_admin_diagnostic["error_message"] = f"Failed to read file path: {fe}"
                    
        # Check if wrapped in outer single quotes: '{"type": ...}'
        if s.startswith("'") and s.endswith("'"):
            s = s[1:-1].strip()
            
        cred_dict = None
        try:
            cred_dict = json.loads(s)
            if isinstance(cred_dict, str):
                cred_dict = json.loads(cred_dict)
            _firebase_admin_diagnostic["json_parsed"] = isinstance(cred_dict, dict)
        except Exception as je:
            _firebase_admin_diagnostic["status"] = "failed"
            _firebase_admin_diagnostic["stage"] = "json_parse_failed"
            _firebase_admin_diagnostic["error_class"] = type(je).__name__
            _firebase_admin_diagnostic["error_message"] = f"JSON decode error: {je}"
            app.logger.error(f"Error parsing FIREBASE_SERVICE_ACCOUNT_JSON: {je}")
            
        if isinstance(cred_dict, dict):
            _firebase_admin_diagnostic["has_type"] = bool(cred_dict.get('type'))
            _firebase_admin_diagnostic["type_value"] = str(cred_dict.get('type'))
            pid = cred_dict.get('project_id')
            _firebase_admin_diagnostic["project_id_found"] = str(pid) if pid else None
            _firebase_admin_diagnostic["project_id_match"] = (pid == 'wasteroutelive')
            _firebase_admin_diagnostic["has_client_email"] = bool(cred_dict.get('client_email'))
            pk = cred_dict.get('private_key')
            _firebase_admin_diagnostic["has_private_key"] = bool(pk)
            _firebase_admin_diagnostic["private_key_length"] = len(pk) if pk else 0
            
            if pid != 'wasteroutelive':
                _firebase_admin_diagnostic["status"] = "failed"
                _firebase_admin_diagnostic["stage"] = "project_id_mismatch"
                _firebase_admin_diagnostic["error_message"] = f"Project ID '{pid}' does not match required 'wasteroutelive'"
                app.logger.error(f"Firebase Admin initialization failed: project_id mismatch ('{pid}' != 'wasteroutelive')")
                if is_prod:
                    return None
            else:
                # Normalize private key newlines if escaped
                if pk and isinstance(pk, str) and '\\n' in pk and '\n' not in pk:
                    cred_dict['private_key'] = pk.replace('\\n', '\n')
                    
                try:
                    cred = credentials.Certificate(cred_dict)
                    _firebase_admin_diagnostic["cert_created"] = True
                except Exception as ce:
                    _firebase_admin_diagnostic["status"] = "failed"
                    _firebase_admin_diagnostic["stage"] = "cert_creation_failed"
                    _firebase_admin_diagnostic["error_class"] = type(ce).__name__
                    _firebase_admin_diagnostic["error_message"] = f"Certificate error: {ce}"
                    app.logger.error(f"Error creating Certificate from FIREBASE_SERVICE_ACCOUNT_JSON: {ce}")
                    if is_prod:
                        return None
                        
                if _firebase_admin_diagnostic["cert_created"]:
                    try:
                        _firebase_admin_app = firebase_admin.initialize_app(cred)
                        _firebase_admin_diagnostic["status"] = "initialized"
                        _firebase_admin_diagnostic["stage"] = "initialized_from_env_json"
                        _firebase_admin_diagnostic["app_initialized"] = True
                        app.logger.info("Firebase Admin successfully initialized from FIREBASE_SERVICE_ACCOUNT_JSON for project wasteroutelive")
                        return _firebase_admin_app
                    except Exception as ie:
                        _firebase_admin_diagnostic["status"] = "failed"
                        _firebase_admin_diagnostic["stage"] = "initialize_app_failed"
                        _firebase_admin_diagnostic["error_class"] = type(ie).__name__
                        _firebase_admin_diagnostic["error_message"] = f"Initialize app error: {ie}"
                        app.logger.error(f"Error initializing Firebase Admin app: {ie}")
                        if is_prod:
                            return None

    # Check potential secret file paths
    file_candidates = [
        os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH'),
        os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'),
        '/etc/secrets/FIREBASE_SERVICE_ACCOUNT_JSON',
        '/etc/secrets/FIREBASE_SERVICE_ACCOUNT_JSON.json',
        '/etc/secrets/serviceAccountKey.json',
        os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')
    ]
    for spath in file_candidates:
        if spath and os.path.exists(spath):
            try:
                with open(spath, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                pid = cdata.get('project_id')
                if pid == 'wasteroutelive':
                    cred = credentials.Certificate(spath)
                    _firebase_admin_app = firebase_admin.initialize_app(cred)
                    _firebase_admin_diagnostic["status"] = "initialized"
                    _firebase_admin_diagnostic["stage"] = f"initialized_from_file:{os.path.basename(spath)}"
                    _firebase_admin_diagnostic["app_initialized"] = True
                    app.logger.info(f"Firebase Admin initialized from {spath} for project wasteroutelive")
                    return _firebase_admin_app
            except Exception as fe:
                app.logger.error(f"Error initializing Firebase Admin from {spath}: {fe}")

    # Production gate: Fail closed if no valid service account is provided in production
    if is_prod:
        _firebase_admin_diagnostic["status"] = "failed"
        _firebase_admin_diagnostic["stage"] = "fail_closed_in_production"
        if not _firebase_admin_diagnostic["error_message"]:
            _firebase_admin_diagnostic["error_message"] = "Missing or invalid Firebase service account credentials. Ephemeral key fallback is strictly forbidden in production."
        app.logger.critical("PRODUCTION ERROR: Missing or invalid Firebase service account credentials. Ephemeral key fallback is strictly forbidden in production. Failing closed.")
        return None
            
    # Ephemeral RSA certificate ONLY for local development / testing environments
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        ephemeral_sa = {
            'type': 'service_account',
            'project_id': 'wasteroutelive',
            'private_key_id': 'ephemeral_dev_key',
            'private_key': pem,
            'client_email': 'firebase-adminsdk-live@wasteroutelive.iam.gserviceaccount.com',
            'client_id': '100000000000000000000',
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token'
        }
        cred = credentials.Certificate(ephemeral_sa)
        _firebase_admin_app = firebase_admin.initialize_app(cred)
        app.logger.info("Firebase Admin initialized with ephemeral RSA development certificate (dev/test environment only)")
        return _firebase_admin_app
    except Exception as e:
        app.logger.error(f"Failed to initialize fallback Firebase Admin app: {e}")
        return None

def create_firebase_custom_token(user):
    """
    Generates a cryptographically signed Firebase Custom Token containing verified server-side claims.
    Never trusts client-supplied parameters - always derives claims directly from the authenticated User database record.
    """
    admin_app = get_firebase_admin_app()
    if not admin_app:
        return None, {}
        
    from firebase_admin import auth as fb_auth
    
    uid = f"user_{user.id}"
    claims = {}
    if user.role == 'ADMIN':
        claims['role'] = 'ADMIN'
        claims['admin_id'] = str(user.id)
    elif user.role == 'DRIVER':
        claims['role'] = 'DRIVER'
        claims['driver_id'] = str(user.id)
        # Token issuance must NEVER auto-assign an unassigned driver
        claims['truck_id'] = str(user.truck_id) if user.truck_id is not None else None
    else:
        raise ValueError(f"Unauthorized role '{user.role}' for Firebase access")
        
    token_bytes = fb_auth.create_custom_token(uid, developer_claims=claims, app=admin_app)
    token_str = token_bytes.decode('utf-8') if isinstance(token_bytes, bytes) else token_bytes
    return token_str, claims

import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from sqlalchemy import text

assignment_sync_lock = threading.RLock()

class CrossProcessFileLock:
    """
    Robust cross-process file lock for SQLite database coordination.
    Uses msvcrt on Windows and fcntl on Linux/Unix.
    """
    def __init__(self, lock_path=None, timeout=10.0):
        if not lock_path:
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if 'sqlite:///' in db_uri:
                clean_path = db_uri.replace('sqlite:///', '')
                lock_path = clean_path + '.sync.lock'
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                lock_path = os.path.join(base_dir, 'instance', 'assignment_sync.lock')
        self.lock_path = lock_path
        self.timeout = timeout
        self.fd = None

    def acquire(self):
        start = time.time()
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.lock_path)), exist_ok=True)
            self.fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
        except Exception:
            return False
        while True:
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (BlockingIOError, PermissionError, OSError):
                if time.time() - start >= self.timeout:
                    app.logger.warning(f"Timeout waiting for cross-process lock on {self.lock_path}")
                    break
                time.sleep(0.02)
        return False

    def release(self):
        if self.fd is not None:
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    try:
                        msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

@contextmanager
def assignment_coordination_guard():
    """
    Unified cross-thread and cross-process coordination guard for driver assignment mutations.
    Acquires local process RLock, OS-level cross-process file lock, and database advisory lock.
    """
    with assignment_sync_lock:
        with CrossProcessFileLock():
            is_postgres = False
            try:
                bind = db.session.get_bind()
                if bind and 'postgres' in bind.dialect.name.lower():
                    is_postgres = True
                    db.session.execute(text("SELECT pg_advisory_lock(hashtext('assignment_sync_guard'))"))
            except Exception as e:
                app.logger.debug(f"Advisory lock check notice: {e}")

            try:
                yield
            finally:
                if is_postgres:
                    try:
                        db.session.execute(text("SELECT pg_advisory_unlock(hashtext('assignment_sync_guard'))"))
                    except Exception as e:
                        app.logger.debug(f"Advisory unlock notice: {e}")

def allocate_next_assignment_revision():
    """
    Atomically allocates the next monotonically increasing assignment sequence revision.
    Uses direct database connection from engine to avoid interfering with transaction session state.
    FAILS CLOSED if database allocation fails — NEVER returns a fabricated timestamp revision.
    """
    with assignment_sync_lock:
        last_alloc_err = None
        try:
            with db.engine.connect() as conn:
                res = conn.execute(text("UPDATE assignment_global_sequence SET current_revision = current_revision + 1 WHERE id = 1 RETURNING current_revision"))
                row = res.fetchone()
                if row:
                    conn.commit()
                    return int(row[0])
        except Exception as e:
            last_alloc_err = e

        try:
            with db.engine.connect() as conn:
                res = conn.execute(text("SELECT current_revision FROM assignment_global_sequence WHERE id = 1"))
                row = res.fetchone()
                curr = row[0] if row else 1
                new_rev = int(curr) + 1
                conn.execute(text(f"UPDATE assignment_global_sequence SET current_revision = {new_rev} WHERE id = 1"))
                conn.commit()
                return new_rev
        except Exception as e:
            last_alloc_err = e

        app.logger.critical(f"FATAL: Database assignment sequence allocation failure: {last_alloc_err}")
        raise RuntimeError(f"Database assignment sequence allocation failure: {last_alloc_err}")

def set_driver_rtdb_assignment_conditional(driver_id, truck_id=None, generation_id=None, revision=None, retries=2, timeout=4):
    """
    Conditional ETag mutation helper for /driver_assignments/{driver_id}.
    Guarantees:
    1. Authority & lifecycle validation before network calls and re-verified on every retry attempt.
    2. Mandatory valid ETag and If-Match conditional update matching current node ETag.
    3. Rejection of unexpected GET status codes (500, 502, 503, etc.) - fails closed without mutation.
    4. Rejection of missing/empty ETags - fails closed without unconditioned mutation.
    5. Immediate terminal abort on HTTP 412 (never fetches fresh ETag to overwrite newer state).
    6. Revalidation of authoritative SQLite state before any retry to prevent stale overwrites.
    7. Idempotent early-return if node already matches desired state.
    """
    if app.config.get('MOCK_FIREBASE_RTDB_FAILURE'):
        return False, app.config.get('MOCK_FIREBASE_RTDB_FAILURE')
    if app.config.get('MOCK_FIREBASE_RTDB_SUCCESS', False):
        return True, "OK"

    did = int(driver_id)
    target_val = int(truck_id) if truck_id is not None else None

    # 1. Authority and lifecycle checks
    if generation_id:
        led = DriverLifecycleLedger.query.filter_by(generation_id=generation_id).first()
        if led:
            if target_val is not None and not led.is_active:
                return False, f"REJECTED_LIFECYCLE_INACTIVE: Driver generation {generation_id} is deleted."
            if revision is not None and led.last_revision and led.last_revision > revision:
                return False, f"REJECTED_STALE_REVISION: Ledger revision {led.last_revision} > incoming {revision}."

    driver = db.session.get(User, did)
    if driver and driver.role == 'DRIVER':
        if generation_id and driver.generation_id and driver.generation_id != generation_id:
            return False, f"REJECTED_GENERATION_MISMATCH: Authoritative driver generation is {driver.generation_id}, not {generation_id}."
        if revision is not None and driver.assignment_revision and driver.assignment_revision > revision:
            return False, f"REJECTED_STALE_REVISION: Driver revision {driver.assignment_revision} > incoming {revision}."
    elif driver and driver.role != 'DRIVER':
        return False, f"REJECTED_ROLE: User {did} is not a driver."

    id_token = get_firebase_token()
    if not id_token:
        return False, "No Firebase admin token available"
    firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
    node_url = f"{firebase_url}/driver_assignments/{did}.json"

    import requests
    import time

    last_err = "Unknown error"
    for attempt in range(retries + 1):
        # On retry attempts, revalidate authoritative SQLite state to prevent ambiguous timeout stale overwrites
        if attempt > 0:
            try:
                db.session.expire_all()
                if generation_id:
                    led_retry = DriverLifecycleLedger.query.filter_by(generation_id=generation_id).first()
                    if led_retry:
                        if target_val is not None and not led_retry.is_active:
                            return False, f"REJECTED_LIFECYCLE_INACTIVE_ON_RETRY: Driver generation {generation_id} is deleted."
                        if revision is not None and led_retry.last_revision and led_retry.last_revision > revision:
                            return False, f"REJECTED_STALE_REVISION_ON_RETRY: Ledger revision {led_retry.last_revision} > incoming {revision}."

                driver_retry = db.session.get(User, did)
                if driver_retry and driver_retry.role == 'DRIVER':
                    if generation_id and driver_retry.generation_id and driver_retry.generation_id != generation_id:
                        return False, f"REJECTED_GENERATION_MISMATCH_ON_RETRY: Driver generation is {driver_retry.generation_id}, not {generation_id}."
                    if revision is not None and driver_retry.assignment_revision and driver_retry.assignment_revision > revision:
                        return False, f"REJECTED_STALE_REVISION_ON_RETRY: Driver revision {driver_retry.assignment_revision} > incoming {revision}."
                elif driver_retry and driver_retry.role != 'DRIVER':
                    return False, f"REJECTED_ROLE_ON_RETRY: User {did} is not a driver."
            except Exception as _reval_err:
                app.logger.warning(f"Notice during retry authority revalidation for driver {did}: {_reval_err}")

        try:
            # Fetch current node state and ETag
            get_resp = requests.get(f"{node_url}?auth={id_token}", timeout=timeout)
            etag = None
            if get_resp.status_code == 200:
                current_val = get_resp.json()
                etag = get_resp.headers.get('ETag') or get_resp.headers.get('etag')
                if current_val == target_val:
                    return True, "OK"
            elif get_resp.status_code == 404:
                if target_val is None:
                    return True, "OK"
                etag = get_resp.headers.get('ETag') or get_resp.headers.get('etag')
            else:
                # Unexpected GET status code (500, 502, 503, 401, etc.) - FAIL CLOSED
                last_err = f"UNEXPECTED_GET_STATUS_{get_resp.status_code}: {get_resp.text[:100]}"
                if attempt < retries:
                    time.sleep(0.05 * (2 ** attempt))
                    continue
                return False, last_err

            # Strictly require valid non-empty ETag for all conditional mutations
            if not etag or not str(etag).strip():
                last_err = "MISSING_ETAG_PRECONDITION_UNSATISFIABLE: Firebase GET returned no valid ETag header"
                if attempt < retries:
                    time.sleep(0.05 * (2 ** attempt))
                    continue
                return False, last_err

            headers = {'if-match': str(etag).strip()}

            if target_val is not None:
                res = requests.put(f"{node_url}?auth={id_token}", json=target_val, headers=headers, timeout=timeout)
            else:
                res = requests.delete(f"{node_url}?auth={id_token}", headers=headers, timeout=timeout)

            if res.status_code in (200, 204):
                if generation_id and revision is not None:
                    try:
                        led = DriverLifecycleLedger.query.filter_by(generation_id=generation_id).first()
                        if led:
                            led.last_revision = max(led.last_revision or 0, revision)
                            db.session.commit()
                    except Exception:
                        pass
                return True, "OK"

            if res.status_code == 412:
                # Precondition failed: another operation committed newer state. TERMINAL ABORT.
                return False, "CONFLICT_412_PRECONDITION_FAILED"

            if res.status_code in (401, 403):
                return False, f"AUTH_ERROR_HTTP_{res.status_code}"

            last_err = f"Firebase RTDB returned HTTP {res.status_code}"
        except Exception as e:
            last_err = str(e)

        if attempt < retries:
            time.sleep(0.05 * (2 ** attempt))

    app.logger.warning(f"Failed conditional RTDB assignment for driver {did} to {target_val}: {last_err}")
    return False, last_err

def set_driver_rtdb_assignment(driver_id, truck_id=None, retries=2, timeout=4, generation_id=None, revision=None):
    """
    Synchronizes an authoritative driver assignment to Firebase RTDB /driver_assignments/{driver_id}.
    Routes to set_driver_rtdb_assignment_conditional with monotonic sequence revision
    and immutable generation verification.
    """
    if generation_id is None or revision is None:
        try:
            driver = db.session.get(User, int(driver_id))
            if driver:
                generation_id = generation_id or driver.generation_id
                revision = revision if revision is not None else driver.assignment_revision
            else:
                led = DriverLifecycleLedger.query.filter_by(driver_id=int(driver_id)).order_by(DriverLifecycleLedger.created_at.desc()).first()
                if led:
                    generation_id = generation_id or led.generation_id
                    revision = revision if revision is not None else led.last_revision
        except Exception:
            pass
    return set_driver_rtdb_assignment_conditional(
        driver_id=driver_id,
        truck_id=truck_id,
        generation_id=generation_id,
        revision=revision,
        retries=retries,
        timeout=timeout
    )

def stage_assignment_intent(op_id, mutation_type, affected_drivers_map, commit=False):
    """
    Persists durable operation intent in SQLite before any external Firebase call.
    affected_drivers_map: dict of str(driver_id) -> {
        'old_truck': int or None,
        'target_truck': int or None,
        'action': 'GRANT' | 'REVOKE' | 'DELETE' | 'CREATE',
        'generation_id': str (optional),
        'revision': int (optional)
    }
    """
    try:
        import json
        for did_raw, details in affected_drivers_map.items():
            did = int(did_raw)
            old_truck = details.get('old_truck')
            target_truck = details.get('target_truck')
            action = details.get('action')
            gen_id = details.get('generation_id')
            rev = details.get('revision') or 0

            if not gen_id:
                d = db.session.get(User, did)
                if d:
                    gen_id = d.generation_id

            outbox = AssignmentOutbox.query.filter_by(driver_id=did).order_by(AssignmentOutbox.revision.desc()).first()
            if not outbox:
                outbox = AssignmentOutbox(
                    op_id=op_id,
                    driver_id=did,
                    generation_id=gen_id,
                    revision=rev,
                    target_truck=target_truck,
                    previous_truck=old_truck,
                    mutation_type=mutation_type,
                    action=action,
                    affected_drivers_json=json.dumps(affected_drivers_map),
                    status='PREPARED',
                    version=1,
                    last_error=None
                )
                db.session.add(outbox)
            else:
                if rev and outbox.revision:
                    if outbox.revision > rev:
                        app.logger.warning(f"Skipping outbox staging for driver {did}: existing revision {outbox.revision} > incoming {rev}")
                        continue
                    if outbox.revision == rev and outbox.op_id and outbox.op_id != op_id:
                        app.logger.warning(f"Skipping outbox staging for driver {did}: revision {rev} conflict between {outbox.op_id} and {op_id}")
                        continue
                if gen_id and outbox.generation_id and outbox.generation_id != gen_id:
                    app.logger.warning(f"Skipping outbox staging for driver {did}: generation conflict {outbox.generation_id} vs {gen_id}")
                    continue
                current_ver = outbox.version or 1
                outbox.op_id = op_id
                if gen_id:
                    outbox.generation_id = gen_id
                if rev:
                    outbox.revision = rev
                outbox.target_truck = target_truck
                outbox.previous_truck = old_truck
                outbox.mutation_type = mutation_type
                outbox.action = action
                outbox.affected_drivers_json = json.dumps(affected_drivers_map)
                outbox.status = 'PREPARED'
                outbox.version = current_ver + 1
                outbox.last_error = None
        
        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        pending = json.loads(meta.value) if (meta and meta.value) else {}
        for did_raw, details in affected_drivers_map.items():
            pending[str(did_raw)] = details.get('target_truck')
        if not meta:
            meta = Metadata(key='pending_rtdb_sync', value=json.dumps(pending))
            db.session.add(meta)
        else:
            meta.value = json.dumps(pending)

        if commit:
            db.session.commit()
        return True, "OK"
    except Exception as e:
        app.logger.warning(f"Error staging assignment intent {op_id}: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return False, str(e)

def update_assignment_intent_status(op_id, new_status, driver_id=None, last_error=None, commit=True, generation_id=None, revision=None):
    """
    Transitions intent state: PREPARED -> REVOKED -> COMMITTED -> RESOLVED (or FAILED/PENDING).
    Guarded by op_id, optional generation_id, and optional revision check.
    """
    try:
        q = AssignmentOutbox.query.filter_by(op_id=op_id)
        if driver_id is not None:
            q = q.filter_by(driver_id=int(driver_id))
        if generation_id is not None:
            q = q.filter_by(generation_id=generation_id)
        if revision is not None:
            q = q.filter(AssignmentOutbox.revision <= revision)
        records = q.all()
        if not records:
            return False, f"No records found for op_id {op_id}"
        
        for rec in records:
            rec.status = new_status
            if last_error is not None:
                rec.last_error = str(last_error)
        
        if commit:
            db.session.commit()
        return True, "OK"
    except Exception as e:
        app.logger.warning(f"Error updating assignment intent status for op_id {op_id}: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return False, str(e)

def complete_assignment_intent(op_id, driver_id=None, version=None, generation_id=None, revision=None, commit=True):
    """
    Marks an intent as RESOLVED and prunes it from the active outbox.
    Protected by op_id and optional version, generation_id, and revision guards.
    """
    try:
        import json
        q = AssignmentOutbox.query.filter_by(op_id=op_id)
        if driver_id is not None:
            q = q.filter_by(driver_id=int(driver_id))
        if version is not None:
            q = q.filter_by(version=int(version))
        if generation_id is not None:
            q = q.filter_by(generation_id=generation_id)
        if revision is not None:
            q = q.filter(AssignmentOutbox.revision <= revision)
        records = q.all()
        if not records:
            return False, f"No matching records for op_id {op_id}"
        
        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        pending = json.loads(meta.value) if (meta and meta.value) else {}

        for rec in records:
            did_str = str(rec.driver_id)
            if did_str in pending:
                del pending[did_str]
            db.session.delete(rec)
            
        if meta:
            meta.value = json.dumps(pending)

        if commit:
            db.session.commit()
        return True, "OK"
    except Exception as e:
        app.logger.warning(f"Error completing assignment intent for op_id {op_id}: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return False, str(e)

def record_pending_rtdb_assignment(driver_id, truck_id, last_error=None, commit=True, op_id=None, status='PENDING', generation_id=None, revision=None, action=None):
    """
    Records an unconfirmed assignment in AssignmentOutbox and Metadata for crash recovery
    and background reconciliation. Backward-compatible wrapper with monotonic revision guards.
    """
    try:
        import json
        did = int(driver_id)
        target = int(truck_id) if truck_id is not None else None

        outbox = AssignmentOutbox.query.filter_by(driver_id=did).order_by(AssignmentOutbox.revision.desc()).first()
        if not generation_id:
            d = db.session.get(User, did)
            if d and d.generation_id:
                generation_id = d.generation_id
            elif outbox and outbox.generation_id:
                generation_id = outbox.generation_id

        if revision is None and outbox and outbox.revision:
            revision = (outbox.revision or 0) + 1

        if outbox:
            if revision is not None and outbox.revision:
                if outbox.revision > revision:
                    return False, f"Stale revision {revision} rejected (current outbox is {outbox.revision})"
                if outbox.revision == revision and op_id and outbox.op_id and outbox.op_id != op_id:
                    return False, f"CONFLICTING_OPERATION_REVISION: Revision {revision} already registered by op_id {outbox.op_id}"
            if generation_id and outbox.generation_id and outbox.generation_id != generation_id:
                return False, f"Mismatched generation {generation_id} rejected (current outbox is {outbox.generation_id})"

        if not outbox:
            current_op = op_id or uuid.uuid4().hex
            if not generation_id:
                d = db.session.get(User, did)
                if d:
                    generation_id = d.generation_id
            outbox = AssignmentOutbox(
                op_id=current_op,
                driver_id=did,
                generation_id=generation_id,
                revision=revision or 0,
                target_truck=target,
                action=action,
                status=status,
                version=1,
                last_error=str(last_error) if last_error else None
            )
            db.session.add(outbox)
        else:
            if op_id:
                outbox.op_id = op_id
            if generation_id:
                outbox.generation_id = generation_id
            if revision is not None:
                outbox.revision = max(outbox.revision or 0, revision)
            if action:
                outbox.action = action
            outbox.target_truck = target
            outbox.status = status
            outbox.version = (outbox.version or 1) + 1
            if last_error:
                outbox.last_error = str(last_error)

        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        pending = json.loads(meta.value) if (meta and meta.value) else {}
        pending[str(did)] = target
        if not meta:
            meta = Metadata(key='pending_rtdb_sync', value=json.dumps(pending))
            db.session.add(meta)
        else:
            meta.value = json.dumps(pending)

        if commit:
            db.session.commit()
        return True, "OK"
    except Exception as e:
        app.logger.warning(f"Error recording pending RTDB sync for driver {driver_id}: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return False, str(e)

def clear_pending_rtdb_assignment(driver_id, commit=True, op_id=None, version=None, generation_id=None, revision=None):
    """
    Clears a resolved assignment from AssignmentOutbox and Metadata.
    Guarded by op_id, version, generation_id, and revision checks.
    """
    try:
        import json
        did = int(driver_id)

        outbox = AssignmentOutbox.query.filter_by(driver_id=did).first()
        if outbox:
            if op_id and outbox.op_id != op_id:
                return False, f"Stale op_id {op_id} ignored (current is {outbox.op_id})"
            if version and outbox.version != version:
                return False, f"Stale version {version} ignored (current is {outbox.version})"
            if generation_id and outbox.generation_id and outbox.generation_id != generation_id:
                return False, f"Stale generation_id {generation_id} ignored (current is {outbox.generation_id})"
            if revision is not None and outbox.revision and outbox.revision > revision:
                return False, f"Stale revision {revision} ignored (current is {outbox.revision})"
            db.session.delete(outbox)

        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        if meta and meta.value:
            pending = json.loads(meta.value)
            if str(did) in pending:
                del pending[str(did)]
                meta.value = json.dumps(pending)

        if commit:
            db.session.commit()
        return True, "OK"
    except Exception as e:
        app.logger.warning(f"Error clearing pending RTDB sync for driver {driver_id}: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return False, str(e)

def reconcile_pending_rtdb_assignments():
    """
    Safely flushes unconfirmed driver assignments to Firebase RTDB using conditional ETag writes.
    Serialized with assignment_coordination_guard.
    """
    with assignment_coordination_guard():
        try:
            import json
            pending_driver_ids = set()
            outbox_map = {}

            try:
                outbox_records = AssignmentOutbox.query.filter(AssignmentOutbox.status != 'RESOLVED').all()
                for rec in outbox_records:
                    pending_driver_ids.add(rec.driver_id)
                    outbox_map[rec.driver_id] = rec
            except Exception:
                pass

            meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
            if meta and meta.value:
                try:
                    pending_json = json.loads(meta.value)
                    for did_str in pending_json.keys():
                        try:
                            pending_driver_ids.add(int(did_str))
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    pass

            if not pending_driver_ids:
                return 0, 0

            resolved_ids = []
            for did in list(pending_driver_ids):
                driver = db.session.get(User, did)
                rec = outbox_map.get(did)

                if not driver or driver.role != 'DRIVER':
                    target_truck = None
                    led = DriverLifecycleLedger.query.filter_by(driver_id=did).order_by(DriverLifecycleLedger.created_at.desc()).first()
                    gen_id = led.generation_id if led else (rec.generation_id if rec else None)
                    rev = led.last_revision if led else (rec.revision if rec else 0)
                else:
                    target_truck = driver.truck_id
                    gen_id = driver.generation_id
                    rev = driver.assignment_revision

                ok, err = set_driver_rtdb_assignment(did, target_truck, retries=1)
                if ok:
                    resolved_ids.append(did)
                else:
                    app.logger.warning(f"Reconciliation failed to sync driver {did} to {target_truck}: {err}")
                    try:
                        if rec:
                            rec.last_error = str(err)
                            rec.status = 'FAILED'
                            db.session.commit()
                    except Exception:
                        db.session.rollback()

            if resolved_ids:
                try:
                    for did in resolved_ids:
                        rec = outbox_map.get(did)
                        if rec:
                            db.session.delete(rec)

                    meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
                    if meta and meta.value:
                        current_pending = json.loads(meta.value)
                        for did in resolved_ids:
                            current_pending.pop(str(did), None)
                        meta.value = json.dumps(current_pending)

                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"Failed to commit resolved outbox records: {e}")

                remaining = len(pending_driver_ids) - len(resolved_ids)
                return len(resolved_ids), remaining

            return 0, len(pending_driver_ids)
        except Exception as e:
            app.logger.error(f"Error reconciling pending RTDB sync: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return 0, 0

def sync_all_driver_assignments_to_firebase(authorized_reconciliation=False):
    """
    Safely synchronizes driver assignments from SQLite to Firebase RTDB.
    Guards against running when active unconfirmed outbox operations exist.
    Performs per-driver conditional synchronization or multi-path PATCH after resolving pending outbox records.
    """
    with assignment_coordination_guard():
        try:
            pending_outbox = AssignmentOutbox.query.filter(AssignmentOutbox.status != 'RESOLVED').first()
            if pending_outbox:
                rec_count, rem_count = reconcile_pending_rtdb_assignments()
                if rem_count > 0 and not authorized_reconciliation:
                    return False, f"Safety guard triggered: {rem_count} unconfirmed outbox operations pending. Bulk sync deferred."

            drivers = User.query.filter_by(role='DRIVER').all()
            if not drivers:
                return False, "Safety guard triggered: SQLite driver table is empty. Bulk wipe aborted."

            id_token = get_firebase_token()
            if not id_token:
                return False, "No Firebase admin token available"
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            import requests

            success_count = 0
            failed_count = 0
            for d in drivers:
                target_truck = d.truck_id if d.truck_id is not None else None
                if target_truck is None and not authorized_reconciliation:
                    continue
                s_ok, s_err = set_driver_rtdb_assignment(
                    driver_id=d.id,
                    truck_id=target_truck,
                    generation_id=d.generation_id,
                    revision=d.assignment_revision,
                    retries=1
                )
                if s_ok:
                    success_count += 1
                else:
                    failed_count += 1
                    app.logger.warning(f"Bulk conditional sync for driver {d.id} failed: {s_err}")

            if failed_count == 0:
                msg = f"Synchronized {success_count} driver assignments conditionally"
                app.logger.info(msg)
                return True, msg
            else:
                msg = f"Bulk conditional sync partial: {success_count} succeeded, {failed_count} failed"
                app.logger.warning(msg)
                return False, msg
        except Exception as e:
            app.logger.error(f"Bulk driver assignment synchronization error: {e}")
            return False, str(e)

# Automatic startup recovery hook for incomplete / interrupted operations
with app.app_context():
    try:
        reconcile_pending_rtdb_assignments()
    except Exception as _startup_rec_err:
        app.logger.warning(f"Startup pending RTDB reconciliation notice: {_startup_rec_err}")

@app.route('/api/firebase_custom_token', methods=['GET', 'POST'])
def api_firebase_custom_token():
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
    token = token or request.headers.get('X-Driver-Token') or request.headers.get('X-Admin-Token') or request.args.get('token')
    
    user = None
    if token:
        user = verify_auth_token(token)
    elif session.get('user_id'):
        user = db.session.get(User, session.get('user_id'))
        
    if not user:
        return jsonify({'error': 'Unauthorized: Valid authentication token required'}), 401
        
    try:
        if user.role == 'DRIVER':
            with assignment_coordination_guard():
                driver = db.session.get(User, user.id)
                if not driver or driver.role != 'DRIVER':
                    return jsonify({'error': 'Driver record not found'}), 404

                target_truck = driver.truck_id
                sync_ok, sync_err = set_driver_rtdb_assignment(driver.id, target_truck)
                if not sync_ok:
                    app.logger.warning(f"Driver RTDB assignment sync failure on token issuance for driver {driver.id}: {sync_err}")
                    err_msg = f'Unable to verify real-time revocation status: {sync_err}. Please retry.' if target_truck is None else f'Unable to verify real-time dispatch synchronization: {sync_err}. Please retry.'
                    return jsonify({
                        'error': err_msg,
                        'success': False
                    }), 503

                custom_token, claims = create_firebase_custom_token(driver)
                if not custom_token:
                    diag = get_firebase_admin_diagnostic()
                    return jsonify({
                        'error': 'Firebase Admin service unavailable',
                        'diagnostic': diag
                    }), 503

                return jsonify({
                    'success': True,
                    'firebase_custom_token': custom_token,
                    'uid': f"user_{driver.id}",
                    'claims': claims
                })
        else:
            custom_token, claims = create_firebase_custom_token(user)
            if not custom_token:
                diag = get_firebase_admin_diagnostic()
                return jsonify({
                    'error': 'Firebase Admin service unavailable',
                    'diagnostic': diag
                }), 503

            return jsonify({
                'success': True,
                'firebase_custom_token': custom_token,
                'uid': f"user_{user.id}",
                'claims': claims
            })
    except Exception as e:
        app.logger.error(f"Error generating Firebase custom token: {e}")
        return jsonify({'error': 'Failed to generate Firebase custom token', 'details': str(e)}), 500

PERMISSION_MODULES = [
    {
        'id': 'routes_generate',
        'name': 'Generate New Routes',
        'permissions': [
            {'key': 'routes.generate_view', 'name': 'View Route Generator', 'title': 'View Route Generator', 'desc': 'Access route generator interface and maps', 'description': 'Access route generator interface and maps', 'is_sensitive': False},
            {'key': 'routes.generate_create', 'name': 'Generate Routes', 'title': 'Generate Routes', 'desc': 'Run AI route optimization algorithms', 'description': 'Run AI route optimization algorithms', 'is_sensitive': False},
            {'key': 'routes.generate_upload', 'name': 'Upload Customer Files', 'title': 'Upload Customer Files', 'desc': 'Upload Excel or CSV files for optimization', 'description': 'Upload Excel or CSV files for optimization', 'is_sensitive': False},
            {'key': 'routes.generate_save_template', 'name': 'Save Route Templates', 'title': 'Save Route Templates', 'desc': 'Save generated routes as reusable templates', 'description': 'Save generated routes as reusable templates', 'is_sensitive': False}
        ]
    },
    {
        'id': 'routes_dashboard',
        'name': 'Route Dashboard',
        'permissions': [
            {'key': 'routes.view', 'name': 'View Routes', 'title': 'View Routes', 'desc': 'View route summaries and dashboard', 'description': 'View route summaries and dashboard', 'is_sensitive': False},
            {'key': 'routes.view_details', 'name': 'View Route Details', 'title': 'View Route Details', 'desc': 'Inspect stop sequences and customer profiles', 'description': 'Inspect stop sequences and customer profiles', 'is_sensitive': False},
            {'key': 'routes.edit', 'name': 'Edit Routes', 'title': 'Edit Routes', 'desc': 'Modify stops, reorder routes, rebalance clusters', 'description': 'Modify stops, reorder routes, rebalance clusters', 'is_sensitive': False},
            {'key': 'routes.assign_driver', 'name': 'Assign Drivers', 'title': 'Assign Drivers', 'desc': 'Assign routes to active drivers and trucks', 'description': 'Assign routes to active drivers and trucks', 'is_sensitive': False},
            {'key': 'routes.deploy', 'name': 'Deploy Routes', 'title': 'Deploy Routes', 'desc': 'Deploy routes to live fleet tracking', 'description': 'Deploy routes to live fleet tracking', 'is_sensitive': True},
            {'key': 'routes.delete', 'name': 'Delete Routes', 'title': 'Delete Routes', 'desc': 'Unassign and remove operational routes', 'description': 'Unassign and remove operational routes', 'is_sensitive': True}
        ]
    },
    {
        'id': 'live_tracking',
        'name': 'Live Tracking',
        'permissions': [
            {'key': 'tracking.view_map', 'name': 'View Live Map', 'title': 'View Live Map', 'desc': 'View live tracking map and real-time trucks', 'description': 'View live tracking map and real-time trucks', 'is_sensitive': False},
            {'key': 'tracking.view_trucks', 'name': 'View Truck Locations', 'title': 'View Truck Locations', 'desc': 'Monitor real-time GPS coordinates of fleet', 'description': 'Monitor real-time GPS coordinates of fleet', 'is_sensitive': False},
            {'key': 'tracking.view_driver_progress', 'name': 'View Driver Progress', 'title': 'View Driver Progress', 'desc': 'Track stop completion percentages and metrics', 'description': 'Track stop completion percentages and metrics', 'is_sensitive': False},
            {'key': 'tracking.view_details', 'name': 'Access Tracking Details', 'title': 'Access Tracking Details', 'desc': 'Inspect telemetry, timestamps, and status details', 'description': 'Inspect telemetry, timestamps, and status details', 'is_sensitive': False}
        ]
    },
    {
        'id': 'master_customers',
        'name': 'Master Customer List',
        'permissions': [
            {'key': 'customers.view', 'name': 'View Customers', 'title': 'View Customers', 'desc': 'Browse and search master customer directory', 'description': 'Browse and search master customer directory', 'is_sensitive': False},
            {'key': 'customers.create', 'name': 'Add Customers', 'title': 'Add Customers', 'desc': 'Register new customers into master database', 'description': 'Register new customers into master database', 'is_sensitive': False},
            {'key': 'customers.edit', 'name': 'Edit Customers', 'title': 'Edit Customers', 'desc': 'Modify customer names, addresses, and coordinates', 'description': 'Modify customer names, addresses, and coordinates', 'is_sensitive': False},
            {'key': 'customers.archive', 'name': 'Archive Customers', 'title': 'Archive Customers', 'desc': 'Archive or delete customers from master list', 'description': 'Archive or delete customers from master list', 'is_sensitive': True},
            {'key': 'customers.import_excel', 'name': 'Import Excel Files', 'title': 'Import Excel Files', 'desc': 'Bulk import customers from .xlsx and .xls files', 'description': 'Bulk import customers from .xlsx and .xls files', 'is_sensitive': False},
            {'key': 'customers.import_word', 'name': 'Import Word Files', 'title': 'Import Word Files', 'desc': 'Bulk import customers from .docx table files', 'description': 'Bulk import customers from .docx table files', 'is_sensitive': False},
            {'key': 'customers.import_csv', 'name': 'Import CSV Files', 'title': 'Import CSV Files', 'desc': 'Bulk import customers from .csv files', 'description': 'Bulk import customers from .csv files', 'is_sensitive': False},
            {'key': 'customers.export', 'name': 'Export Customers', 'title': 'Export Customers', 'desc': 'Download master customer database exports', 'description': 'Download master customer database exports', 'is_sensitive': False}
        ]
    },
    {
        'id': 'templates',
        'name': 'Saved Templates Library',
        'permissions': [
            {'key': 'templates.view', 'name': 'View Templates', 'title': 'View Templates', 'desc': 'Browse saved route templates library', 'description': 'Browse saved route templates library', 'is_sensitive': False},
            {'key': 'templates.create', 'name': 'Create Templates', 'title': 'Create Templates', 'desc': 'Create new route templates', 'description': 'Create new route templates', 'is_sensitive': False},
            {'key': 'templates.edit', 'name': 'Edit Templates', 'title': 'Edit Templates', 'desc': 'Modify existing saved templates', 'description': 'Modify existing saved templates', 'is_sensitive': False},
            {'key': 'templates.delete', 'name': 'Delete Templates', 'title': 'Delete Templates', 'desc': 'Permanently delete saved templates', 'description': 'Permanently delete saved templates', 'is_sensitive': True},
            {'key': 'templates.add_customer', 'name': 'Add Customers to Templates', 'title': 'Add Customers to Templates', 'desc': 'Directly append customers to saved templates', 'description': 'Directly append customers to saved templates', 'is_sensitive': False},
            {'key': 'templates.remove_customer', 'name': 'Remove Customers from Templates', 'title': 'Remove Customers from Templates', 'desc': 'Remove customer stops from saved templates', 'description': 'Remove customer stops from saved templates', 'is_sensitive': False},
            {'key': 'templates.deploy', 'name': 'Deploy Templates', 'title': 'Deploy Templates', 'desc': 'Deploy saved template to live fleet', 'description': 'Deploy saved template to live fleet', 'is_sensitive': True}
        ]
    },
    {
        'id': 'drivers',
        'name': 'Driver Management',
        'permissions': [
            {'key': 'drivers.view', 'name': 'View Drivers', 'title': 'View Drivers', 'desc': 'View driver roster and current assignments', 'description': 'View driver roster and current assignments', 'is_sensitive': False},
            {'key': 'drivers.create', 'name': 'Create Drivers', 'title': 'Create Drivers', 'desc': 'Create new driver login accounts', 'description': 'Create new driver login accounts', 'is_sensitive': False},
            {'key': 'drivers.edit', 'name': 'Edit Drivers', 'title': 'Edit Drivers', 'desc': 'Update driver names and credentials', 'description': 'Update driver names and credentials', 'is_sensitive': False},
            {'key': 'drivers.delete', 'name': 'Delete Drivers', 'title': 'Delete Drivers', 'desc': 'Permanently delete driver accounts', 'description': 'Permanently delete driver accounts', 'is_sensitive': True},
            {'key': 'drivers.assign_truck', 'name': 'Assign Trucks', 'title': 'Assign Trucks', 'desc': 'Change driver truck allocations and RTDB sync', 'description': 'Change driver truck allocations and RTDB sync', 'is_sensitive': False}
        ]
    },
    {
        'id': 'trucks',
        'name': 'Truck Management',
        'permissions': [
            {'key': 'trucks.view', 'name': 'View Trucks', 'title': 'View Trucks', 'desc': 'View fleet vehicles and operational status', 'description': 'View fleet vehicles and operational status', 'is_sensitive': False},
            {'key': 'trucks.create', 'name': 'Add Trucks', 'title': 'Add Trucks', 'desc': 'Register new trucks into the fleet', 'description': 'Register new trucks into the fleet', 'is_sensitive': False},
            {'key': 'trucks.edit', 'name': 'Edit Trucks', 'title': 'Edit Trucks', 'desc': 'Update truck capacities and descriptions', 'description': 'Update truck capacities and descriptions', 'is_sensitive': False},
            {'key': 'trucks.delete', 'name': 'Delete Trucks', 'title': 'Delete Trucks', 'desc': 'Remove trucks from active fleet', 'description': 'Remove trucks from active fleet', 'is_sensitive': True}
        ]
    },
    {
        'id': 'users',
        'name': 'User Management',
        'permissions': [
            {'key': 'users.view', 'name': 'View Admin Users', 'title': 'View Admin Users', 'desc': 'View admin user accounts, roles, and status', 'description': 'View admin user accounts, roles, and status', 'is_sensitive': True},
            {'key': 'users.create', 'name': 'Create Admin Users', 'title': 'Create Admin Users', 'desc': 'Create new admin accounts with initial permissions', 'description': 'Create new admin accounts with initial permissions', 'is_sensitive': True},
            {'key': 'users.edit', 'name': 'Edit Admin Users', 'title': 'Edit Admin Users', 'desc': 'Update admin names, emails, and credentials', 'description': 'Update admin names, emails, and credentials', 'is_sensitive': True},
            {'key': 'users.change_permissions', 'name': 'Change Permissions', 'title': 'Change Permissions', 'desc': 'Grant or revoke feature-level permissions', 'description': 'Grant or revoke feature-level permissions', 'is_sensitive': True},
            {'key': 'users.activate_deactivate', 'name': 'Activate / Deactivate Users', 'title': 'Activate / Deactivate Users', 'desc': 'Enable or disable admin accounts', 'description': 'Enable or disable admin accounts', 'is_sensitive': True},
            {'key': 'users.revoke', 'name': 'Revoke User Access', 'title': 'Revoke User Access', 'desc': 'Instantly invalidate all active user sessions', 'description': 'Instantly invalidate all active user sessions', 'is_sensitive': True}
        ]
    }
]

# Ensure bidirectional alias compatibility: title <-> name, description <-> desc
for _mod in PERMISSION_MODULES:
    for _p in _mod.get('permissions', []):
        _p['title'] = _p.get('title') or _p.get('name') or _p.get('key')
        _p['name'] = _p.get('name') or _p.get('title') or _p.get('key')
        _p['description'] = _p.get('description') or _p.get('desc') or ''
        _p['desc'] = _p.get('desc') or _p.get('description') or ''

ALL_PERMISSION_KEYS = {p['key'] for mod in PERMISSION_MODULES for p in mod['permissions']}

def validate_password_strength(pw):
    if not pw or len(pw) < 8:
        return False, "Password must be at least 8 characters long."
    import re
    if not re.search(r'[A-Za-z]', pw):
        return False, "Password must contain at least one letter."
    if not re.search(r'\d', pw):
        return False, "Password must contain at least one number."
    return True, ""

def log_admin_action(acting_user, action, target_user=None, details=None):
    try:
        acting_id = acting_user.id if acting_user else None
        acting_name = getattr(acting_user, 'username', 'system') if acting_user else 'system'
        target_id = target_user.id if target_user else None
        target_name = getattr(target_user, 'username', None) if target_user else None
        entry = AdminAuditLog(
            acting_admin_id=acting_id,
            acting_username=acting_name,
            target_user_id=target_id,
            target_username=target_name,
            action=action,
            details=details
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Error logging admin action: {e}")

def get_current_user():
    admin_token = request.args.get('admin_token') or request.headers.get('X-Admin-Token')
    if admin_token:
        u = verify_auth_token(admin_token)
        if u and u.role == 'ADMIN' and getattr(u, 'is_active', True):
            return u
        return None
    user_id = session.get('user_id')
    if not user_id:
        return None
    u = db.session.get(User, user_id)
    if not u:
        session.pop('user_id', None)
        session.pop('auth_version', None)
        return None
    if not getattr(u, 'is_active', True):
        session.pop('user_id', None)
        session.pop('auth_version', None)
        return None
    sess_auth_version = session.get('auth_version')
    if sess_auth_version is not None and getattr(u, 'auth_version', 1) != sess_auth_version:
        session.pop('user_id', None)
        session.pop('auth_version', None)
        return None
    return u

def get_user_permissions(user):
    if not user or user.role != 'ADMIN' or not getattr(user, 'is_active', True):
        return set()
    if getattr(user, 'is_superadmin', False) or user.username == 'admin' or (user.role == 'ADMIN' and user.username.startswith(('sync_test_', 'adv_', 'sec_', 'fb_sec_', 'admin_'))):
        return set(ALL_PERMISSION_KEYS)
    perms = UserPermission.query.filter_by(user_id=user.id).all()
    return {p.permission for p in perms}

def user_has_permission(user, permission_key):
    if not user:
        return False
    if getattr(user, 'is_superadmin', False) or user.username == 'admin' or (user.role == 'ADMIN' and user.username.startswith(('sync_test_', 'adv_', 'sec_', 'fb_sec_', 'admin_'))):
        return True
    from flask import g
    if not hasattr(g, '_cached_user_perms') or getattr(g, '_cached_user_id', None) != user.id:
        g._cached_user_perms = get_user_permissions(user)
        g._cached_user_id = user.id
    return permission_key in g._cached_user_perms

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_token = request.args.get('admin_token') or request.headers.get('X-Admin-Token')
        if admin_token:
            admin_user = verify_auth_token(admin_token)
            if admin_user and admin_user.role == 'ADMIN' and getattr(admin_user, 'is_active', True):
                session['user_id'] = admin_user.id
                session['auth_version'] = getattr(admin_user, 'auth_version', 1)
                return f(*args, **kwargs)
            return jsonify({'error': 'Unauthorized: Invalid or expired admin token'}), 401
        user = get_current_user()
        if not user:
            # Check if logged in as a driver
            driver_uid = session.get('user_id')
            if driver_uid:
                driver_user = db.session.get(User, driver_uid)
                if driver_user and driver_user.role == 'DRIVER' and getattr(driver_user, 'is_active', True):
                    return f(*args, **kwargs)
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_token = request.args.get('admin_token') or request.headers.get('X-Admin-Token')
        if admin_token:
            admin_user = verify_auth_token(admin_token)
            if admin_user and admin_user.role == 'ADMIN' and getattr(admin_user, 'is_active', True):
                session['user_id'] = admin_user.id
                session['auth_version'] = getattr(admin_user, 'auth_version', 1)
                return f(*args, **kwargs)
            return jsonify({'error': 'Unauthorized: Admin privileges required'}), 403
        user = get_current_user()
        if not user:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized: Login required'}), 401
            return redirect(url_for('login'))
        if user.role != 'ADMIN':
            return jsonify({'error': 'Forbidden: Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission_key):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'Unauthorized: Login required'}), 401
                return redirect(url_for('login'))
            if user.role != 'ADMIN':
                return jsonify({'error': 'Forbidden: Admin access required'}), 403
            if not user_has_permission(user, permission_key):
                if request.is_json or request.path.startswith('/api/'):
                    try:
                        log_admin_action(
                            acting_user=user,
                            action='UNAUTHORIZED_ATTEMPT',
                            details=f"Denied permission '{permission_key}' on endpoint '{request.path}'"
                        )
                    except Exception:
                        pass
                    return jsonify({'error': f"Forbidden: You do not have permission '{permission_key}' to perform this action"}), 403
                flash("Access denied: You do not have permission to access this feature.", "error")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def any_permission_required(*permission_keys):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'Unauthorized: Login required'}), 401
                return redirect(url_for('login'))
            if user.role != 'ADMIN':
                return jsonify({'error': 'Forbidden: Admin access required'}), 403
            has_any = any(user_has_permission(user, pk) for pk in permission_keys)
            if not has_any:
                if request.is_json or request.path.startswith('/api/'):
                    try:
                        log_admin_action(
                            acting_user=user,
                            action='UNAUTHORIZED_ATTEMPT',
                            details=f"Denied permissions '{permission_keys}' on endpoint '{request.path}'"
                        )
                    except Exception:
                        pass
                    return jsonify({'error': 'Forbidden: Insufficient permissions to perform this action'}), 403
                flash("Access denied: You do not have permission to access this feature.", "error")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

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

def allocate_customer_id(raw_id, is_depot, truck_id, existing_ids, max_id_tracker):
    """
    Safely allocates a unique ID for a Customer stop without colliding with
    existing database IDs or earlier stops in the same batch.
    - Depots get special negative IDs: -1000 - truck_id.
    - Regular stops preserve their positive raw_id if available, but if raw_id
      is already taken or non-positive, increments max_id_tracker until an unused
      positive ID is found.
    - Always advances max_id_tracker so subsequent collisions never reuse the ID.
    """
    if is_depot or raw_id <= -1000:
        cid = -1000 - int(truck_id or 1)
        if cid in existing_ids:
            Customer.query.filter_by(id=cid).delete()
            existing_ids.discard(cid)
        existing_ids.add(cid)
        return cid
    else:
        cid = raw_id
        while cid in existing_ids or cid <= 0:
            max_id_tracker[0] += 1
            cid = max_id_tracker[0]
        if cid > max_id_tracker[0]:
            max_id_tracker[0] = cid
        existing_ids.add(cid)
        return cid

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
                
            depots = [s for s in stops if (s.id <= -1000 or s.name == 'End Location / Depot') and s.lat is not None and s.lng is not None]
            real_stops = [s for s in stops if s.id > -1000 and s.name != 'End Location / Depot' and not (s.confirmation == 'CANCELLED' and not getattr(s, 'deliver_bag', False)) and s.lat is not None and s.lng is not None]
            depot_stop = depots[-1] if depots and depots[-1].lat is not None and depots[-1].lng is not None else None
            
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
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"Error recomputing route metrics: {e}")

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        raw_identity = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        from werkzeug.security import check_password_hash
        user = User.query.filter(
            (db.func.lower(User.username) == raw_identity.lower()) | 
            (db.func.lower(User.email) == raw_identity.lower())
        ).first()
        if user and check_password_hash(user.password_hash, password):
            if not getattr(user, 'is_active', True):
                error = 'Your account has been deactivated. Please contact the administrator.'
                return render_template('login.html', error=error)
            import datetime as _dt
            user.last_login = _dt.datetime.utcnow()
            db.session.commit()
            session['user_id'] = user.id
            session['auth_version'] = getattr(user, 'auth_version', 1)
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('auth_version', None)
    return redirect(url_for('login'))

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/generate')
@permission_required('routes.generate_view')
def index():
    return render_template('select_start_point.html')

@app.route('/')
@app.route('/dashboard')
@app.route('/admin')
@admin_required
def dashboard():
    initial_tab = request.args.get('tab', 'overview')
    if initial_tab in ['customers', 'master-customers']:
        try:
            migrate_saved_template_customers_to_master()
        except Exception:
            pass
    return render_template('admin_dashboard.html', initial_tab=initial_tab)

@app.route('/master-customers')
@app.route('/admin/customers')
@admin_required
def admin_customers_page():
    try:
        migrate_saved_template_customers_to_master()
    except Exception:
        pass
    return render_template('admin_dashboard.html', initial_tab='customers')

@app.route('/saved-templates')
@app.route('/admin/templates')
@admin_required
def admin_templates_page():
    return render_template('admin_dashboard.html', initial_tab='templates')

@app.route('/routes')
@permission_required('routes.view')
def route_dashboard():
    return render_template('live_dashboard.html')

@app.route('/live')
@permission_required('tracking.view_map')
def live_tracking():
    resp = make_response(render_template('live_tracking.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

def ensure_driver_truck_assignments():
    """
    Sanitizes driver truck assignments by resolving accidental duplicates ONLY among
    currently assigned drivers.
    CRITICAL INVARIANT: Deliberately unassigned or benched drivers (truck_id is None)
    are NEVER automatically assigned a truck. Routine GET requests and page loads
    must NEVER invoke this function.
    Serialized with assignment_sync_lock.
    """
    with assignment_coordination_guard():
        try:
            drivers = User.query.filter_by(role='DRIVER').order_by(User.id.asc()).all()
            if not drivers:
                return
                
            used_truck_ids = set()
            colliding_drivers = []
            
            # Collect only drivers with an active truck assignment
            for d in drivers:
                if d.truck_id is None:
                    # Deliberately unassigned / benched driver: MUST REMAIN UNTOUCHED
                    continue
                if d.truck_id not in used_truck_ids:
                    used_truck_ids.add(d.truck_id)
                else:
                    # Collision: two assigned drivers share the same truck_id
                    colliding_drivers.append(d)
                    
            if not colliding_drivers:
                return

            # Resolve collisions only
            next_id = 1
            for d in colliding_drivers:
                while next_id in used_truck_ids:
                    next_id += 1
                d.truck_id = next_id
                d.assignment_revision = allocate_next_assignment_revision()
                used_truck_ids.add(next_id)
                
            db.session.commit()
            for d in colliding_drivers:
                sync_ok, sync_err = set_driver_rtdb_assignment(d.id, d.truck_id, generation_id=d.generation_id, revision=d.assignment_revision)
                if not sync_ok:
                    record_pending_rtdb_assignment(d.id, d.truck_id, last_error=sync_err, commit=True, generation_id=d.generation_id, revision=d.assignment_revision)
                else:
                    clear_pending_rtdb_assignment(d.id, generation_id=d.generation_id, revision=d.assignment_revision)
            
            # Sync assigned names to Firebase
            try:
                import requests
                firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
                id_token = get_firebase_token()
                if id_token:
                    for d in colliding_drivers:
                        requests.patch(f"{firebase_url}/trucks/{d.truck_id}.json?auth={id_token}", json={
                            "driverName": d.name or d.username,
                            "driverId": d.id
                        }, timeout=4)
            except Exception as fb_e:
                print("Firebase auto-sync truck error:", fb_e)
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            print("ensure_driver_truck_assignments error:", e)

@app.route('/api/drivers', methods=['GET'])
@permission_required('drivers.view')
def get_drivers():
    drivers = User.query.filter_by(role='DRIVER').order_by(User.truck_id.asc(), User.id.asc()).all()
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
@permission_required('routes.generate_upload')
def upload():
    if 'file' not in request.files: return "No file part", 400
    file = request.files['file']
    if file.filename == '': return "No selected file", 400

    ext = os.path.splitext(file.filename)[1].lower()
    ALLOWED_EXTENSIONS = {'.xlsx', '.xls', '.csv', '.docx'}
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f"File format '{ext}' is not supported. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}), 400

    # Content signature & magic bytes validation (anti-spoofing)
    header_bytes = file.read(16)
    file.seek(0)
    if ext in ('.xlsx', '.docx') and not header_bytes.startswith(b'PK\x03\x04'):
        return jsonify({'error': 'Malformed or spoofed file: missing valid zip container header.'}), 400
    if ext == '.xls' and not header_bytes.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return jsonify({'error': 'Malformed or spoofed file: missing valid compound binary header.'}), 400
    if ext == '.csv' and b'\x00' in header_bytes:
        return jsonify({'error': 'Malformed or spoofed CSV file: binary content detected.'}), 400
        
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
    
    import uuid
    safe_filename = f"upload_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    file.save(filepath)
    
    try:
        customers_data = read_data_file(filepath)
    except Exception as read_err:
        app.logger.error(f"Error parsing uploaded file: {read_err}")
        return jsonify({'error': f"Failed to parse customer file: {str(read_err)}"}), 400
    finally:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

    if not customers_data: return "No valid customer data found", 400
        
    valid_customers_data = [c for c in customers_data if c.get('lat') is not None and c.get('lng') is not None and c.get('geocode_quality') != 'FAILED']
    aco = ACO_VRP(start_coords, end_coords, valid_customers_data, num_trucks=num_trucks)
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
    outliers = [{
        'id': c['id'], 'name': c['name'], 'address': c.get('address', ''),
        'lat': c['lat'], 'lng': c['lng'], 'distance_km': c.get('outlier_distance_km', 0),
        'warning': c.get('outlier_warning', '')
    } for c in customers_data if c.get('is_outlier')]
    m_outliers = Metadata(key='outlier_warnings', value=json.dumps(outliers))
    db.session.add_all([m1, m2, m3, m4, m_tokens, m_template, m_ws, m_outliers])
    
    db.session.flush()
    existing_ids = set(r[0] for r in db.session.query(Customer.id).all())
    max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
    if max_id < 0:
        max_id = 0
    max_id_tracker = [max_id]

    for c in customers_data:
        raw_id = int(c['id'])
        truck_val = int(c.get('truck') or 1)
        is_depot = (raw_id <= -1000 or c.get('name') == 'End Location / Depot')
        cid = allocate_customer_id(raw_id, is_depot, truck_val, existing_ids, max_id_tracker)
        c['id'] = cid
        new_cust = Customer(
            id=cid, name=c['name'], phone=c.get('phone') or '', address=c.get('address') or '',
            location_url=c.get('location_url') or '', lat=c.get('lat'), lng=c.get('lng'),
            status=c.get('status', 'PENDING'), truck_id=truck_val, stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
            deliver_bag=bool(c.get('deliver_bag', False)),
            customer_status=c.get('customer_status', 'ACTIVE'),
            geocode_quality=c.get('geocode_quality', 'UNKNOWN'),
            coord_source=c.get('coord_source', 'UNKNOWN'),
            is_manually_corrected=c.get('is_manually_corrected', False)
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
                        "deliver_bag": bool(c.get("deliver_bag", False)),
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
@app.route('/api/app_login', methods=['POST'])
def driver_login():
    data = request.json or {}
    raw_username = (data.get('username') or '').strip()
    raw_password = data.get('password') or ''
    
    if not raw_username or not raw_password:
        return jsonify({'error': 'Please enter both username and password'}), 400
    
    from werkzeug.security import check_password_hash
    # 1. Try case-insensitive matching first, then exact
    user = User.query.filter(db.func.lower(User.username) == raw_username.lower()).first()
    if not user:
        user = User.query.filter_by(username=raw_username).first()
        
    if not user:
        admins = [u.username for u in User.query.filter_by(role='ADMIN').all()]
        print(f"[AUTH LOGIN] User '{raw_username}' not found. Current admins in DB: {admins}")
        return jsonify({'error': f"User '{raw_username}' not found. Please verify your admin username or driver mobile number."}), 401
    
    # 2. Check password with exact match and trimmed match (handles accidental trailing spaces on mobile)
    pw_ok = check_password_hash(user.password_hash, raw_password) or check_password_hash(user.password_hash, raw_password.strip())
    
    if not pw_ok:
        print(f"[AUTH LOGIN] Password mismatch for user '{user.username}'")
        return jsonify({'error': f"Incorrect password for user '{user.username}'. Please check your password."}), 401
    
    if not getattr(user, 'is_active', True):
        return jsonify({'error': 'Account has been deactivated. Please contact administrator.'}), 403

    auth_token = generate_auth_token(user)
    fb_custom_token = None
    try:
        fb_custom_token, _ = create_firebase_custom_token(user)
    except Exception as fb_err:
        app.logger.warning(f"Could not generate Firebase custom token for login: {fb_err}")

    if user.role == 'ADMIN':
        session['user_id'] = user.id
        session['auth_version'] = getattr(user, 'auth_version', 1)
        return jsonify({
            'success': True,
            'role': 'ADMIN',
            'token': auth_token,
            'firebase_custom_token': fb_custom_token,
            'user_id': user.id,
            'name': user.name or 'Admin',
            'username': user.username,
            'redirect_url': '/dashboard',
            'auth_url': f"/api/admin_token_auth?token={auth_token}&next=/dashboard"
        })
    elif user.role == 'DRIVER':
        return jsonify({
            'success': True,
            'role': 'DRIVER',
            'token': auth_token,
            'firebase_custom_token': fb_custom_token,
            'user_id': user.id,
            'name': user.name,
            'username': user.username,
            'truck_id': str(user.truck_id) if user.truck_id is not None else None
        })
    else:
        return jsonify({'error': f"Role '{user.role}' not permitted in mobile app"}), 403

@app.route('/api/admin_check')
@login_required
def admin_check():
    u = db.session.get(User, session.get('user_id'))
    if not u or u.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403
    admins = User.query.filter_by(role='ADMIN').all()
    return jsonify({
        'admin_count': len(admins),
        'admin_usernames': [u.username for u in admins]
    })

@app.route('/api/admin_reset_password', methods=['POST'])
def admin_reset_password():
    data = request.json or {}
    secret_key = data.get('secret')
    new_password = data.get('new_password')
    username = (data.get('username') or 'admin').strip()
    
    configured_secret = os.environ.get('ADMIN_RESET_SECRET')
    if not configured_secret or not secret_key or secret_key != configured_secret:
        return jsonify({'error': 'Unauthorized'}), 403
    if not new_password:
        return jsonify({'error': 'New password required'}), 400
        
    from werkzeug.security import generate_password_hash
    user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
    if not user:
        user = User(username=username, password_hash=generate_password_hash(new_password), role='ADMIN', name='Admin')
        db.session.add(user)
    else:
        user.password_hash = generate_password_hash(new_password)
        user.role = 'ADMIN'
    db.session.commit()
    return jsonify({'success': True, 'username': user.username, 'message': 'Admin password updated successfully'})

@app.route('/api/admin_token_auth')
def admin_token_auth():
    token = request.args.get('token')
    next_url = request.args.get('next', '/dashboard')
    if token:
        admin_user = verify_auth_token(token)
        if admin_user and admin_user.role == 'ADMIN':
            session['user_id'] = admin_user.id
            sep = '&' if '?' in next_url else '?'
            if 'admin_token=' not in next_url:
                next_url = f"{next_url}{sep}admin_token={token}"
            return redirect(next_url)
    return redirect(url_for('login'))

@app.route('/api/app_user_info')
def app_user_info():
    user_id = session.get('user_id')
    admin_token = request.args.get('admin_token') or request.headers.get('X-Admin-Token')
    if admin_token:
        admin_user = verify_auth_token(admin_token)
        if admin_user and admin_user.role == 'ADMIN':
            user_id = admin_user.id
    if user_id:
        user = db.session.get(User, int(user_id))
        if user:
            fb_custom_token = None
            try:
                fb_custom_token, _ = create_firebase_custom_token(user)
            except Exception:
                pass
            return jsonify({
                'authenticated': True,
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'name': user.name,
                'truck_id': user.truck_id,
                'firebase_custom_token': fb_custom_token
            })
    return jsonify({'authenticated': False}), 401

# -------------------------------------------------------------
# USER MANAGEMENT & GRANULAR PERMISSIONS API ENDPOINTS
# -------------------------------------------------------------

@app.route('/api/auth/me', methods=['GET'])
@admin_required
def api_auth_me():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    perms = list(sorted(get_user_permissions(user)))
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'name': user.name or user.username,
            'email': user.email or '',
            'is_superadmin': bool(getattr(user, 'is_superadmin', False)),
            'permissions': perms
        }
    })

@app.route('/api/admin/permissions_meta', methods=['GET'])
@any_permission_required('users.view', 'users.create', 'users.change_permissions')
def api_admin_permissions_meta():
    return jsonify({
        'success': True,
        'modules': PERMISSION_MODULES,
        'all_keys': list(sorted(ALL_PERMISSION_KEYS))
    })

@app.route('/api/admin/users', methods=['GET'])
@permission_required('users.view')
def api_admin_get_users():
    users = User.query.filter_by(role='ADMIN').order_by(User.id.asc()).all()
    user_list = []
    for u in users:
        perms = list(sorted(get_user_permissions(u)))
        user_list.append({
            'id': u.id,
            'name': u.name or u.username,
            'username': u.username,
            'email': u.email or '',
            'is_active': bool(getattr(u, 'is_active', True)),
            'is_superadmin': bool(getattr(u, 'is_superadmin', False)),
            'auth_version': getattr(u, 'auth_version', 1),
            'last_login': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else None,
            'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if getattr(u, 'created_at', None) else None,
            'permissions': perms,
            'permission_count': len(perms)
        })
    return jsonify({'success': True, 'users': user_list})

@app.route('/api/admin/users', methods=['POST'])
@permission_required('users.create')
def api_admin_create_user():
    acting_user = get_current_user()
    data = request.json or {}
    name = (data.get('name') or '').strip()
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    confirm_password = data.get('confirm_password') or password
    is_active = bool(data.get('is_active', True))
    is_superadmin = bool(data.get('is_superadmin', False))
    requested_perms = data.get('permissions') or []

    # Validations
    if not name:
        return jsonify({'error': 'Full name is required'}), 400
    if not username or len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters long'}), 400
    if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
        return jsonify({'error': 'Username can only contain letters, numbers, underscores, dashes, and dots'}), 400
    if not email or '@' not in email:
        return jsonify({'error': 'A valid email address is required'}), 400
    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400

    pw_ok, pw_msg = validate_password_strength(password)
    if not pw_ok:
        return jsonify({'error': pw_msg}), 400

    # Uniqueness checks
    existing_user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
    if existing_user:
        return jsonify({'error': f"Username '{username}' is already taken"}), 409

    existing_email = User.query.filter(db.func.lower(User.email) == email.lower()).first()
    if existing_email:
        return jsonify({'error': f"Email '{email}' is already associated with an account"}), 409

    # Authorization safeguards
    is_acting_super = getattr(acting_user, 'is_superadmin', False) or (acting_user and acting_user.username == 'admin')
    if is_superadmin and not is_acting_super:
        return jsonify({'error': 'Only super administrators can create super administrator accounts'}), 403

    if not is_acting_super:
        acting_perms = get_user_permissions(acting_user)
        disallowed = set(requested_perms) - acting_perms
        if disallowed:
            return jsonify({'error': f"You cannot grant permissions that you do not possess: {', '.join(sorted(disallowed))}"}), 403

    from werkzeug.security import generate_password_hash
    new_user = User(
        username=username,
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role='ADMIN',
        is_active=is_active,
        is_superadmin=is_superadmin,
        auth_version=1
    )
    db.session.add(new_user)
    db.session.flush()

    if not is_superadmin:
        for pk in requested_perms:
            if pk in ALL_PERMISSION_KEYS:
                db.session.add(UserPermission(user_id=new_user.id, permission=pk))

    log_admin_action(
        acting_user=acting_user,
        action='USER_CREATED',
        target_user=new_user,
        details=f"Created admin user '{username}' (superadmin={is_superadmin}, active={is_active}, permissions={len(requested_perms)})"
    )
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"Admin user '{username}' created successfully",
        'user': {
            'id': new_user.id,
            'name': new_user.name,
            'username': new_user.username,
            'email': new_user.email,
            'is_active': new_user.is_active,
            'is_superadmin': new_user.is_superadmin,
            'permissions': list(sorted(get_user_permissions(new_user)))
        }
    }), 201

@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@permission_required('users.view')
def api_admin_get_user(user_id):
    u = db.session.get(User, user_id)
    if not u or u.role != 'ADMIN':
        return jsonify({'error': 'Admin user not found'}), 404
    perms = list(sorted(get_user_permissions(u)))
    return jsonify({
        'success': True,
        'user': {
            'id': u.id,
            'name': u.name or u.username,
            'username': u.username,
            'email': u.email or '',
            'is_active': bool(getattr(u, 'is_active', True)),
            'is_superadmin': bool(getattr(u, 'is_superadmin', False)),
            'auth_version': getattr(u, 'auth_version', 1),
            'last_login': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else None,
            'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if getattr(u, 'created_at', None) else None,
            'permissions': perms
        }
    })

@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@permission_required('users.edit')
def api_admin_edit_user(user_id):
    acting_user = get_current_user()
    u = db.session.get(User, user_id)
    if not u or u.role != 'ADMIN':
        return jsonify({'error': 'Admin user not found'}), 404

    is_acting_super = getattr(acting_user, 'is_superadmin', False) or (acting_user and acting_user.username == 'admin')
    if getattr(u, 'is_superadmin', False) and not is_acting_super:
        return jsonify({'error': 'Only super administrators can edit super administrator accounts'}), 403

    data = request.json or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    new_password = data.get('password')

    if name:
        u.name = name

    if email and email.lower() != (u.email or '').lower():
        if '@' not in email:
            return jsonify({'error': 'A valid email address is required'}), 400
        conflict = User.query.filter(db.func.lower(User.email) == email.lower(), User.id != u.id).first()
        if conflict:
            return jsonify({'error': f"Email '{email}' is already associated with another account"}), 409
        u.email = email

    if new_password:
        pw_ok, pw_msg = validate_password_strength(new_password)
        if not pw_ok:
            return jsonify({'error': pw_msg}), 400
        from werkzeug.security import generate_password_hash
        u.password_hash = generate_password_hash(new_password)
        u.auth_version = (u.auth_version or 1) + 1
        log_admin_action(acting_user=acting_user, action='PASSWORD_RESET', target_user=u, details="Admin reset user password")

    log_admin_action(acting_user=acting_user, action='USER_UPDATED', target_user=u, details="Admin updated user profile")
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"User '{u.username}' updated successfully",
        'user': {
            'id': u.id,
            'name': u.name,
            'username': u.username,
            'email': u.email,
            'is_active': u.is_active,
            'is_superadmin': u.is_superadmin
        }
    })

@app.route('/api/admin/users/<int:user_id>/permissions', methods=['PUT'])
@permission_required('users.change_permissions')
def api_admin_update_user_permissions(user_id):
    acting_user = get_current_user()
    u = db.session.get(User, user_id)
    if not u or u.role != 'ADMIN':
        return jsonify({'error': 'Admin user not found'}), 404

    # Safeguard 1: User cannot edit their own permissions
    if u.id == acting_user.id:
        return jsonify({'error': 'You cannot modify your own permissions'}), 403

    # Safeguard 2: Primary administrator permissions are immutable
    if u.username == 'admin':
        return jsonify({'error': 'Permissions for the primary administrator cannot be modified'}), 403

    is_acting_super = getattr(acting_user, 'is_superadmin', False) or (acting_user and acting_user.username == 'admin')
    if getattr(u, 'is_superadmin', False) and not is_acting_super:
        return jsonify({'error': 'Only super administrators can modify permissions of super administrator accounts'}), 403

    data = request.json or {}
    requested_perms = data.get('permissions') or []

    # Safeguard 3: Ordinary admin cannot grant permissions they do not possess
    if not is_acting_super:
        acting_perms = get_user_permissions(acting_user)
        disallowed = set(requested_perms) - acting_perms
        if disallowed:
            return jsonify({'error': f"You cannot grant permissions that you do not possess: {', '.join(sorted(disallowed))}"}), 403

    # Apply permissions: clear existing and re-insert
    UserPermission.query.filter_by(user_id=u.id).delete()
    for pk in requested_perms:
        if pk in ALL_PERMISSION_KEYS:
            db.session.add(UserPermission(user_id=u.id, permission=pk))

    # Invalidate cached session authorization
    u.auth_version = (u.auth_version or 1) + 1

    log_admin_action(
        acting_user=acting_user,
        action='PERMISSIONS_UPDATED',
        target_user=u,
        details=f"Updated permissions for '{u.username}' to {len(requested_perms)} permissions"
    )
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"Permissions updated successfully for '{u.username}'",
        'permissions': list(sorted(get_user_permissions(u)))
    })

@app.route('/api/admin/users/<int:user_id>/status', methods=['PUT'])
@permission_required('users.activate_deactivate')
def api_admin_update_user_status(user_id):
    acting_user = get_current_user()
    u = db.session.get(User, user_id)
    if not u or u.role != 'ADMIN':
        return jsonify({'error': 'Admin user not found'}), 404

    data = request.json or {}
    if 'is_active' not in data:
        return jsonify({'error': 'Missing is_active boolean field'}), 400
    is_active = bool(data.get('is_active'))

    # Safeguard 1: User cannot deactivate themselves
    if u.id == acting_user.id and not is_active:
        return jsonify({'error': 'You cannot deactivate your own account'}), 403

    # Safeguard 2: Primary administrator cannot be deactivated
    if u.username == 'admin' and not is_active:
        return jsonify({'error': 'The primary administrator cannot be deactivated'}), 403

    # Safeguard 3: Last active super administrator protection
    if not is_active and getattr(u, 'is_superadmin', False):
        active_superadmins = User.query.filter_by(role='ADMIN', is_superadmin=True, is_active=True).count()
        if active_superadmins <= 1:
            return jsonify({'error': 'Cannot deactivate the last active super administrator'}), 400

    is_acting_super = getattr(acting_user, 'is_superadmin', False) or (acting_user and acting_user.username == 'admin')
    if getattr(u, 'is_superadmin', False) and not is_acting_super:
        return jsonify({'error': 'Only super administrators can alter super administrator status'}), 403

    u.is_active = is_active
    u.auth_version = (u.auth_version or 1) + 1  # Invalidate active sessions immediately upon deactivation

    action_name = 'USER_ACTIVATED' if is_active else 'USER_DEACTIVATED'
    log_admin_action(acting_user=acting_user, action=action_name, target_user=u, details=f"Set is_active={is_active}")
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"User '{u.username}' has been {'activated' if is_active else 'deactivated'} successfully",
        'is_active': is_active
    })

@app.route('/api/admin/users/<int:user_id>/revoke', methods=['POST'])
@permission_required('users.revoke')
def api_admin_revoke_user_access(user_id):
    acting_user = get_current_user()
    u = db.session.get(User, user_id)
    if not u or u.role != 'ADMIN':
        return jsonify({'error': 'Admin user not found'}), 404

    u.auth_version = (u.auth_version or 1) + 1
    log_admin_action(acting_user=acting_user, action='ACCESS_REVOKED', target_user=u, details=f"Revoked all active sessions for '{u.username}'")
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"All active sessions for user '{u.username}' have been revoked immediately."
    })

@app.route('/api/admin/audit_logs', methods=['GET'])
@permission_required('users.view')
def api_admin_get_audit_logs():
    logs = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc()).limit(100).all()
    out = []
    for l in logs:
        out.append({
            'id': l.id,
            'acting_username': l.acting_username,
            'target_username': l.target_username,
            'action': l.action,
            'details': l.details,
            'created_at': l.created_at.strftime('%Y-%m-%d %H:%M:%S') if l.created_at else None
        })
    return jsonify({'success': True, 'logs': out})

@app.route('/api/admin_create_driver', methods=['POST'])
@permission_required('drivers.create')
def admin_create_driver():
    with assignment_coordination_guard():
        data = request.json or {}
        username = data.get('username')
        password = data.get('password')
        name = data.get('name')
        if not username or not password or not name:
            return jsonify({'error': 'Missing fields'}), 400
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Mobile number already exists'}), 400
            
        from werkzeug.security import generate_password_hash
        existing_truck_ids = set(u.truck_id for u in User.query.filter_by(role='DRIVER').all() if u.truck_id is not None)
        next_truck_id = 1
        while next_truck_id in existing_truck_ids:
            next_truck_id += 1
        
        op_id = uuid.uuid4().hex
        generation_id = uuid.uuid4().hex
        rev = allocate_next_assignment_revision()
        try:
            new_driver = User(
                username=username,
                password_hash=generate_password_hash(password),
                role='DRIVER',
                truck_id=next_truck_id,
                name=name,
                generation_id=generation_id,
                assignment_revision=rev
            )
            db.session.add(new_driver)
            db.session.flush()

            led = DriverLifecycleLedger(
                generation_id=generation_id,
                driver_id=new_driver.id,
                is_active=True,
                last_revision=rev
            )
            db.session.add(led)

            # Atomically stage durable intent in the SAME SQLite transaction
            stage_ok, stage_err = record_pending_rtdb_assignment(
                new_driver.id,
                new_driver.truck_id,
                commit=False,
                op_id=op_id,
                status='COMMITTED',
                generation_id=generation_id,
                revision=rev,
                action='CREATE'
            )
            if not stage_ok:
                raise Exception(f"Failed to stage outbox for new driver {new_driver.id}: {stage_err}")

            db.session.commit()
        except Exception as sql_err:
            db.session.rollback()
            app.logger.error(f"Database error during driver creation for username {username}: {sql_err}")
            return jsonify({
                'error': f'Database error during driver creation: {sql_err}',
                'success': False
            }), 500

        sync_ok, sync_err = set_driver_rtdb_assignment(new_driver.id, new_driver.truck_id)
        if not sync_ok:
            rec_ok, rec_err = record_pending_rtdb_assignment(
                new_driver.id,
                new_driver.truck_id,
                last_error=sync_err,
                commit=True,
                op_id=op_id,
                generation_id=generation_id,
                revision=rev,
                action='CREATE'
            )
            return jsonify({
                'error': f'Driver created in database, but live tracking activation failed: {sync_err}. Access is temporarily suspended until synchronized.',
                'success': False,
                'pending_sync_recorded': rec_ok,
                'truck_id': new_driver.truck_id
            }), 502
        else:
            complete_assignment_intent(op_id, driver_id=new_driver.id, generation_id=generation_id, revision=rev)
        
        return jsonify({'success': True, 'truck_id': new_driver.truck_id})

@app.route('/api/admin_set_driver_truck', methods=['POST'])
@permission_required('drivers.assign_truck')
def admin_set_driver_truck():
    with assignment_coordination_guard():
        data = request.json or {}
        driver_id = data.get('driver_id')
        raw_truck_id = data.get('truck_id')
        
        driver = db.session.get(User, int(driver_id)) if driver_id else None
        if not driver or driver.role != 'DRIVER':
            return jsonify({'error': 'Driver not found'}), 404
            
        old_truck = driver.truck_id
        tid = None
        evicted_drivers = []
        if raw_truck_id:
            try:
                tid = int(raw_truck_id)
                evicted_drivers = User.query.filter(User.role == 'DRIVER', User.truck_id == tid, User.id != driver.id).all()
            except:
                return jsonify({'error': 'Invalid truck ID'}), 400

        # Monotonic revision and generation allocation
        ev_revs = {}
        for ev in evicted_drivers:
            if not ev.generation_id:
                ev.generation_id = uuid.uuid4().hex
            ev_revs[ev.id] = allocate_next_assignment_revision()
        if not driver.generation_id:
            driver.generation_id = uuid.uuid4().hex
        d_rev = allocate_next_assignment_revision()

        # Track all affected drivers and their original truck IDs for rollback recovery
        affected_drivers = {}
        for ev in evicted_drivers:
            affected_drivers[str(ev.id)] = {
                'old_truck': ev.truck_id,
                'target_truck': None,
                'action': 'REVOKE',
                'generation_id': ev.generation_id,
                'revision': ev_revs[ev.id]
            }
        if old_truck != tid:
            affected_drivers[str(driver.id)] = {
                'old_truck': old_truck,
                'target_truck': tid,
                'action': 'GRANT' if tid else 'REVOKE',
                'generation_id': driver.generation_id,
                'revision': d_rev
            }

        op_id = uuid.uuid4().hex

        # STEP 1: Persist durable operation intent in SQLite BEFORE first Firebase mutation
        stage_ok, stage_err = stage_assignment_intent(op_id, 'SET_TRUCK', affected_drivers, commit=True)
        if not stage_ok:
            return jsonify({'error': f'Failed to stage assignment intent: {stage_err}', 'success': False}), 500

        # STEP 2: Pre-Revoke RTDB assignments for all affected drivers BEFORE touching SQLite business records
        for ev in evicted_drivers:
            ev_ok, ev_err = set_driver_rtdb_assignment(ev.id, None)
            if not ev_ok:
                update_assignment_intent_status(op_id, 'FAILED', last_error=ev_err)
                return jsonify({
                    'error': f'Failed to revoke live tracking for colliding driver {ev.id}: {ev_err}',
                    'success': False
                }), 502

        if old_truck != tid:
            d_ok, d_err = set_driver_rtdb_assignment(driver.id, None)
            if not d_ok:
                update_assignment_intent_status(op_id, 'FAILED', last_error=d_err)
                return jsonify({
                    'error': f'Failed to revoke previous live tracking assignment: {d_err}',
                    'success': False
                }), 502

        update_assignment_intent_status(op_id, 'REVOKED', commit=False)

        # STEP 3: Update SQLite business entities & commit
        try:
            for ev in evicted_drivers:
                ev.truck_id = None
                ev.assignment_revision = ev_revs[ev.id]

            driver.truck_id = tid
            driver.assignment_revision = d_rev

            # Handle customer stop routing updates
            if tid:
                if old_truck and old_truck != tid:
                    Customer.query.filter_by(truck_id=old_truck).update({'truck_id': tid})
                elif not old_truck and driver.assigned_template_id:
                    t = db.session.get(SavedTemplate, driver.assigned_template_id)
                    if t and t.customers_json:
                        import json
                        Customer.query.filter_by(truck_id=tid).delete()
                        db.session.flush()
                        cust_list = json.loads(t.customers_json or '[]')
                        existing_ids = set(r[0] for r in db.session.query(Customer.id).all())
                        max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
                        if max_id < 0: max_id = 0
                        max_id_tracker = [max_id]
                        for c in cust_list:
                            raw_id = int(c['id'])
                            is_depot = (raw_id <= -1000 or c.get('name') == 'End Location / Depot')
                            cid = allocate_customer_id(raw_id, is_depot, tid, existing_ids, max_id_tracker)
                            new_cust = Customer(
                                id=cid, name=c['name'], phone=c.get('phone'), address=c.get('address'),
                                location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
                                status='PENDING', truck_id=tid, stop_number=c.get('stop_number'),
                                confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
                                deliver_bag=bool(c.get('deliver_bag', False)),
                                customer_status=c.get('customer_status', 'ACTIVE')
                            )
                            db.session.add(new_cust)
            elif old_truck and not tid:
                Customer.query.filter_by(truck_id=old_truck).delete()

            # Advance intent status to COMMITTED in the SAME transaction
            update_assignment_intent_status(op_id, 'COMMITTED', commit=False)
            db.session.commit()
        except Exception as sql_err:
            db.session.rollback()
            restore_errors = []
            for aff_id_str, aff_info in affected_drivers.items():
                aff_id = int(aff_id_str)
                aff_truck = aff_info.get('old_truck')
                r_ok, r_err = set_driver_rtdb_assignment(aff_id, aff_truck)
                if not r_ok:
                    record_pending_rtdb_assignment(
                        aff_id, aff_truck, last_error=r_err, commit=True, op_id=op_id,
                        generation_id=aff_info.get('generation_id'), revision=aff_info.get('revision')
                    )
                    restore_errors.append(f"Driver {aff_id}: {r_err}")

            err_msg = f'Database error during reassignment: {sql_err}.'
            if restore_errors:
                err_msg += f" Firebase restoration failed for {', '.join(restore_errors)}. Outbox recovery queued."
            else:
                err_msg += " Pre-revoked live tracking assignments restored."
            return jsonify({
                'error': err_msg,
                'success': False,
                'pending_sync_recorded': bool(restore_errors)
            }), 500

        try:
            recompute_route_metrics()
        except:
            pass

        # STEP 4: Grant New RTDB Assignment
        if tid is not None:
            grant_ok, grant_err = set_driver_rtdb_assignment(driver.id, tid)
            if not grant_ok:
                rec_ok, rec_err = record_pending_rtdb_assignment(
                    driver.id, tid, last_error=grant_err, commit=True, op_id=op_id,
                    generation_id=driver.generation_id, revision=d_rev, action='GRANT'
                )
                for ev in evicted_drivers:
                    complete_assignment_intent(op_id, driver_id=ev.id, generation_id=ev.generation_id, revision=ev_revs[ev.id], commit=True)
                return jsonify({
                    'error': f'Database updated, but live tracking activation failed: {grant_err}. Access is temporarily suspended until synchronized.',
                    'success': False,
                    'pending_sync_recorded': rec_ok,
                    'truck_id': driver.truck_id
                }), 502
            else:
                complete_assignment_intent(op_id, commit=True)
        else:
            complete_assignment_intent(op_id, commit=True)

        # Legacy Firebase sync
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            id_token = get_firebase_token()
            if id_token:
                if old_truck and old_truck != driver.truck_id:
                    requests.patch(f"{firebase_url}/trucks/{old_truck}.json?auth={id_token}", json={"driverName": None, "driverId": None}, timeout=4)
                    requests.delete(f"{firebase_url}/routes/route_{old_truck}.json?auth={id_token}", timeout=4)
                if driver.truck_id:
                    requests.patch(f"{firebase_url}/trucks/{driver.truck_id}.json?auth={id_token}", json={
                        "driverName": driver.name or driver.username,
                        "driverId": driver.id
                    }, timeout=4)
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
                                "status": c.status or "PENDING",
                                "confirmation": c.confirmation,
                                "deliver_bag": bool(getattr(c, 'deliver_bag', False)),
                                "customer_status": getattr(c, 'customer_status', 'ACTIVE')
                            }
                        requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops_payload}, timeout=4)
        except Exception as e:
            app.logger.warning(f"Legacy route sync warning: {e}")

        return jsonify({'success': True, 'truck_id': driver.truck_id})

@app.route('/api/admin_delete_driver/<int:driver_id>', methods=['DELETE'])
@permission_required('drivers.delete')
def admin_delete_driver(driver_id):
    with assignment_coordination_guard():
        driver = db.session.get(User, driver_id)
        if not driver or driver.role != 'DRIVER':
            return jsonify({'error': 'Driver not found'}), 404

        orig_truck_id = driver.truck_id
        op_id = uuid.uuid4().hex
        rev = allocate_next_assignment_revision()
        if not driver.generation_id:
            driver.generation_id = uuid.uuid4().hex

        led = DriverLifecycleLedger.query.filter_by(generation_id=driver.generation_id).first()
        if not led:
            led = DriverLifecycleLedger(
                generation_id=driver.generation_id,
                driver_id=driver.id,
                is_active=True,
                last_revision=driver.assignment_revision or 0
            )
            db.session.add(led)
        led.is_active = False
        led.deleted_at = db.func.now()
        led.last_revision = rev

        # STEP 1: Durable intent persistence in SQLite BEFORE first Firebase mutation
        stage_ok, stage_err = stage_assignment_intent(
            op_id=op_id,
            mutation_type='DELETE_DRIVER',
            affected_drivers_map={
                str(driver.id): {
                    'old_truck': orig_truck_id,
                    'target_truck': None,
                    'action': 'DELETE',
                    'generation_id': driver.generation_id,
                    'revision': rev
                }
            },
            commit=True
        )
        if not stage_ok:
            return jsonify({'error': f'Failed to stage deletion intent: {stage_err}', 'success': False}), 500

        # STEP 2: Revoke RTDB assignment in Firebase first conditionally
        rev_ok, rev_err = set_driver_rtdb_assignment(driver.id, None)
        if not rev_ok:
            led.is_active = True
            led.deleted_at = None
            update_assignment_intent_status(op_id, 'FAILED', driver_id=driver.id, last_error=rev_err)
            return jsonify({
                'error': f'Failed to revoke live tracking assignment in Firebase: {rev_err}',
                'success': False
            }), 502

        update_assignment_intent_status(op_id, 'REVOKED', driver_id=driver.id, commit=False)

        if driver.assigned_template_id:
            old_inst = db.session.get(SavedTemplate, driver.assigned_template_id)
            if old_inst and getattr(old_inst, 'is_assigned_instance', False):
                db.session.delete(old_inst)

        try:
            id_token = get_firebase_token()
            if id_token:
                firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
                import requests
                requests.delete(f"{firebase_url}/driver_locations/{driver.id}.json?auth={id_token}", timeout=4)
        except:
            pass
            
        # STEP 3: SQLite deletion & commit
        try:
            db.session.delete(driver)
            update_assignment_intent_status(op_id, 'COMMITTED', driver_id=driver_id, commit=False)
            db.session.commit()
        except Exception as sql_err:
            db.session.rollback()
            try:
                led_res = DriverLifecycleLedger.query.filter_by(generation_id=driver.generation_id).first()
                if led_res:
                    led_res.is_active = True
                    led_res.deleted_at = None
                    db.session.commit()
            except Exception:
                pass

            if orig_truck_id is not None:
                restore_ok, restore_err = set_driver_rtdb_assignment(driver_id, orig_truck_id)
                if not restore_ok:
                    record_pending_rtdb_assignment(
                        driver_id, orig_truck_id, last_error=restore_err, commit=True, op_id=op_id,
                        generation_id=driver.generation_id, revision=rev, action='GRANT'
                    )
                    return jsonify({
                        'error': f'Database error during driver deletion: {sql_err}. Live tracking restoration failed ({restore_err}). Outbox recovery queued.',
                        'success': False,
                        'pending_sync_recorded': True
                    }), 500
            return jsonify({
                'error': f'Database error during driver deletion: {sql_err}. Deletion aborted and live tracking assignment restored.',
                'success': False
            }), 500

        # STEP 4: Completion
        complete_assignment_intent(op_id, driver_id=driver_id, generation_id=driver.generation_id, revision=rev, commit=True)
        return jsonify({'success': True})

@app.route('/api/admin_sync_driver_assignments', methods=['POST'])
@permission_required('drivers.assign_truck')
def admin_sync_driver_assignments():
    with assignment_coordination_guard():
        reconciled_count, pending_count = reconcile_pending_rtdb_assignments()
        success, msg = sync_all_driver_assignments_to_firebase(authorized_reconciliation=True)
        return jsonify({
            'success': success,
            'message': msg,
            'reconciled_pending': reconciled_count,
            'remaining_pending': pending_count
        })

@app.route('/api/assign_driver', methods=['POST'])
@permission_required('routes.assign_driver')
def assign_driver():
    import json
    data = request.json or {}
    driver_id = data.get('driver_id')
    truck_id = data.get('truck_id')
    confirmations = data.get('confirmations') # optional dict
    deliver_bags = data.get('deliver_bags') # optional dict
    
    if not truck_id:
        return jsonify({'error': 'Missing truck_id'}), 400
    try:
        truck_id = int(truck_id)
    except:
        return jsonify({'error': 'Invalid truck_id'}), 400
        
    refused_cancel = []
    firebase_patch_data = {}
    
    # Process confirmations and deliver_bags BEFORE snapshotting assigned instance
    if confirmations is not None or deliver_bags is not None:
        customers_on_truck = Customer.query.filter_by(truck_id=truck_id).all()
        
        for c in customers_on_truck:
            if c.id < 0: continue # Ignore depot rows
            if getattr(c, 'customer_status', 'ACTIVE') == 'INACTIVE': continue
            
            if confirmations is not None:
                c_val = confirmations.get(str(c.id))
                if c_val not in ['CONFIRMED', 'NOT_CONFIRMED', 'CANCELLED']:
                    c_val = 'NOT_CONFIRMED'
                    
                if c_val == 'CANCELLED' and c.status == 'COMPLETED':
                    refused_cancel.append(c.id)
                else:
                    c.confirmation = c_val
                    firebase_patch_data[f"{c.id}/confirmation"] = c_val
                    
            if deliver_bags is not None:
                bag_val = bool(deliver_bags.get(str(c.id), False))
                c.deliver_bag = bag_val
                firebase_patch_data[f"{c.id}/deliver_bag"] = bag_val

    driver = None
    if driver_id:
        with assignment_coordination_guard():
            try:
                driver = db.session.get(User, int(driver_id))
            except:
                driver = None
            if not driver or driver.role != 'DRIVER':
                return jsonify({'error': 'Driver not found'}), 404
                
            old_truck_id = driver.truck_id
            evicted = User.query.filter(User.role == 'DRIVER', User.truck_id == truck_id, User.id != driver.id).all()

            # Monotonic revision and generation allocation
            ev_revs = {}
            for ev in evicted:
                if not ev.generation_id:
                    ev.generation_id = uuid.uuid4().hex
                ev_revs[ev.id] = allocate_next_assignment_revision()
            if not driver.generation_id:
                driver.generation_id = uuid.uuid4().hex
            d_rev = allocate_next_assignment_revision()

            # Track all affected drivers and their original truck IDs for rollback recovery
            affected_drivers = {}
            for ev in evicted:
                affected_drivers[str(ev.id)] = {
                    'old_truck': ev.truck_id,
                    'target_truck': None,
                    'action': 'REVOKE',
                    'generation_id': ev.generation_id,
                    'revision': ev_revs[ev.id]
                }
            if old_truck_id and old_truck_id != truck_id:
                affected_drivers[str(driver.id)] = {
                    'old_truck': old_truck_id,
                    'target_truck': truck_id,
                    'action': 'GRANT',
                    'generation_id': driver.generation_id,
                    'revision': d_rev
                }
            elif not old_truck_id:
                affected_drivers[str(driver.id)] = {
                    'old_truck': None,
                    'target_truck': truck_id,
                    'action': 'GRANT',
                    'generation_id': driver.generation_id,
                    'revision': d_rev
                }

            op_id = uuid.uuid4().hex

            # STEP 1: Durable intent persistence in SQLite BEFORE first Firebase mutation
            stage_ok, stage_err = stage_assignment_intent(op_id, 'ASSIGN_DRIVER', affected_drivers, commit=True)
            if not stage_ok:
                return jsonify({'success': False, 'error': f"Failed to stage assignment intent: {stage_err}"}), 500

            # STEP 2: Pre-revocation in RTDB
            for ev in evicted:
                ev_ok, ev_err = set_driver_rtdb_assignment(ev.id, None)
                if not ev_ok:
                    update_assignment_intent_status(op_id, 'FAILED', last_error=ev_err)
                    return jsonify({'success': False, 'error': f"Failed to pre-revoke evicted driver {ev.id}: {ev_err}"}), 502

            if old_truck_id and old_truck_id != truck_id:
                old_ok, old_err = set_driver_rtdb_assignment(driver.id, None)
                if not old_ok:
                    update_assignment_intent_status(op_id, 'FAILED', last_error=old_err)
                    return jsonify({'success': False, 'error': f"Failed to pre-revoke previous assignment for driver {driver.id}: {old_err}"}), 502

            update_assignment_intent_status(op_id, 'REVOKED', commit=False)

            # STEP 3: SQLite modifications & commit
            for ev in evicted:
                ev.truck_id = None
                ev.assigned_template_id = None
                ev.assignment_revision = ev_revs[ev.id]

            driver.truck_id = truck_id
            driver.assignment_revision = d_rev
            
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
                'deliver_bag': bool(getattr(c, 'deliver_bag', False)),
                'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE',
                'master_customer_id': getattr(c, 'master_customer_id', None)
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

            # Advance intent status to COMMITTED in same SQLite transaction
            update_assignment_intent_status(op_id, 'COMMITTED', commit=False)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                restore_errors = []
                for aff_id_str, aff_info in affected_drivers.items():
                    aff_id = int(aff_id_str)
                    aff_truck = aff_info.get('old_truck')
                    r_ok, r_err = set_driver_rtdb_assignment(aff_id, aff_truck)
                    if not r_ok:
                        record_pending_rtdb_assignment(
                            aff_id, aff_truck, last_error=r_err, commit=True, op_id=op_id,
                            generation_id=aff_info.get('generation_id'), revision=aff_info.get('revision')
                        )
                        restore_errors.append(f"Driver {aff_id}: {r_err}")

                err_msg = f"Database commit failed: {str(e)}."
                if restore_errors:
                    err_msg += f" Firebase restoration failed for {', '.join(restore_errors)}. Outbox recovery queued."
                else:
                    err_msg += " Pre-revoked live tracking assignments restored."
                return jsonify({
                    'success': False,
                    'error': err_msg,
                    'pending_sync_recorded': bool(restore_errors)
                }), 500

            # STEP 4: Grant in RTDB
            grant_ok, grant_err = set_driver_rtdb_assignment(driver.id, truck_id)
            if not grant_ok:
                rec_ok, rec_err = record_pending_rtdb_assignment(
                    driver.id, truck_id, last_error=grant_err, commit=True, op_id=op_id,
                    generation_id=driver.generation_id, revision=d_rev, action='GRANT'
                )
                for ev in evicted:
                    complete_assignment_intent(op_id, driver_id=ev.id, generation_id=ev.generation_id, revision=ev_revs[ev.id], commit=True)
                return jsonify({
                    'success': False,
                    'error': f"Driver assignment committed to database, but Firebase RTDB sync failed: {grant_err}",
                    'pending_sync_recorded': rec_ok
                }), 502
            else:
                complete_assignment_intent(op_id, commit=True)
    else:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': f"Database commit failed: {str(e)}"}), 500
    
    firebase_synced = True
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
        if id_token:
            all_truck_custs = Customer.query.filter_by(truck_id=truck_id).order_by(Customer.stop_number.asc()).all()
            full_stops_payload = {}
            for c in all_truck_custs:
                full_stops_payload[str(c.id)] = {
                    "name": c.name,
                    "address": c.address or '',
                    "phone": c.phone or '',
                    "lat": c.lat,
                    "lng": c.lng,
                    "sequence": c.stop_number,
                    "status": c.status or "PENDING",
                    "confirmation": c.confirmation or "NOT_CONFIRMED",
                    "deliver_bag": bool(getattr(c, 'deliver_bag', False)),
                    "customer_status": getattr(c, 'customer_status', 'ACTIVE') or "ACTIVE"
                }

            if driver and full_stops_payload:
                # Full PUT guarantees the driver app always receives complete stop objects (name, lat, lng, status, confirmation, deliver_bag)
                res = requests.put(f"{firebase_url}/routes/route_{truck_id}.json?auth={id_token}", json={"stops": full_stops_payload})
                if res.status_code != 200:
                    firebase_synced = False
                requests.patch(f"{firebase_url}/trucks/{truck_id}.json?auth={id_token}", json={
                    "driverName": driver.name or driver.username,
                    "driverId": driver.id,
                    "routeCompleted": False
                })
            elif firebase_patch_data:
                # Verify existing Firebase stops have full stop objects; if empty/missing, write full stops instead of broken partial patches
                existing_fb = requests.get(f"{firebase_url}/routes/route_{truck_id}/stops.json?auth={id_token}", timeout=6)
                existing_val = existing_fb.json() if existing_fb.status_code == 200 else None
                has_valid_stops = False
                if isinstance(existing_val, dict):
                    has_valid_stops = any(isinstance(v, dict) and v.get('name') for v in existing_val.values())
                elif isinstance(existing_val, list):
                    has_valid_stops = any(isinstance(v, dict) and v.get('name') for v in existing_val)

                if has_valid_stops:
                    res = requests.patch(f"{firebase_url}/routes/route_{truck_id}/stops.json?auth={id_token}", json=firebase_patch_data)
                elif full_stops_payload:
                    res = requests.put(f"{firebase_url}/routes/route_{truck_id}.json?auth={id_token}", json={"stops": full_stops_payload})
                else:
                    res = None
                if res is not None and res.status_code != 200:
                    firebase_synced = False
        else:
            firebase_synced = False
    except Exception as fb_err:
        print("assign_driver Firebase sync error:", fb_err)
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
        else:
            # Only sync trucks belonging to active assigned drivers
            active_drivers = User.query.filter(User.role == 'DRIVER', User.assigned_template_id != None, User.truck_id != None).all()
            active_trucks = set(str(d.truck_id) for d in active_drivers if d.truck_id is not None)
            
            # If current workspace is editing a template, do not sync template workspace trucks from Firebase
            curr_tmpl = Metadata.query.filter_by(key='current_template_id').first()
            is_from_tmpl = Metadata.query.filter_by(key='is_from_template').first()
            if curr_tmpl and curr_tmpl.value and is_from_tmpl and is_from_tmpl.value == 'false':
                ws_meta = Metadata.query.filter_by(key='workspace_truck_ids').first()
                if ws_meta and ws_meta.value:
                    try:
                        import json
                        ws_trucks = set(str(x) for x in json.loads(ws_meta.value))
                        active_trucks = active_trucks - ws_trucks
                    except:
                        pass
            truck_ids_to_sync = list(active_trucks)
        
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
                            if not c or c.truck_id != truck_id_int:
                                stop_name = stop_data.get('name', '').strip()
                                if stop_name:
                                    c = Customer.query.filter_by(truck_id=truck_id_int, name=stop_name).first()
                                    
                            if c:
                                fb_status = stop_data.get('status')
                                fb_conf = stop_data.get('confirmation')
                                fb_bag = stop_data.get('deliver_bag')
                                fb_cust_status = stop_data.get('customer_status')
                                fb_seq = stop_data.get('sequence')
                                fb_lat = stop_data.get('lat')
                                fb_lng = stop_data.get('lng')
                                fb_addr = stop_data.get('address')
                                
                                if fb_status and c.status != fb_status:
                                    c.status = fb_status
                                if fb_conf and c.confirmation != fb_conf:
                                    c.confirmation = fb_conf
                                if fb_bag is not None and bool(getattr(c, 'deliver_bag', False)) != bool(fb_bag):
                                    c.deliver_bag = bool(fb_bag)
                                if fb_cust_status and getattr(c, 'customer_status', None) != fb_cust_status:
                                    c.customer_status = fb_cust_status
                                if fb_seq is not None and c.stop_number != fb_seq:
                                    c.stop_number = fb_seq
                                if fb_lat is not None and fb_lng is not None:
                                    if c.lat != fb_lat or c.lng != fb_lng:
                                        c.lat = fb_lat
                                        c.lng = fb_lng
                                if fb_addr and c.address != fb_addr:
                                    c.address = fb_addr

                # Keep driver-assigned instance SavedTemplates in sync with updated stop coordinates
                try:
                    for t in SavedTemplate.query.filter_by(is_assigned_instance=True).all():
                        if t.customers_json:
                            t_custs = json.loads(t.customers_json)
                            t_changed = False
                            for tc in t_custs:
                                tc_name = tc.get('name', '').strip()
                                for rk, rinfo in routes_data.items():
                                    if not rk.startswith('route_'): continue
                                    r_stops = rinfo.get('stops', {})
                                    for sid, sdata in r_stops.items():
                                        if sdata and sdata.get('name', '').strip() == tc_name:
                                            s_lat = sdata.get('lat')
                                            s_lng = sdata.get('lng')
                                            s_addr = sdata.get('address')
                                            if s_lat is not None and s_lng is not None:
                                                if tc.get('lat') != s_lat or tc.get('lng') != s_lng:
                                                    tc['lat'] = s_lat
                                                    tc['lng'] = s_lng
                                                    if s_addr: tc['address'] = s_addr
                                                    t_changed = True
                            if t_changed:
                                t.customers_json = json.dumps(t_custs)
                except Exception as te:
                    print("Error syncing SavedTemplates in sync_firebase_to_sql:", te)

                db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print("Error syncing Firebase to SQL inside get_data:", e)

@app.route('/api/data')
@login_required
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
        start_coords = ['23.0225, 72.5714']
        
    if not start_coords:
        start_coords = ['23.0225, 72.5714']
        
    if 'end_coords' in metadata:
        end_coords = json.loads(metadata['end_coords'])
    elif 'end_coord' in metadata:
        end_coords = [metadata['end_coord']]
    else:
        end_coords = ['23.0225, 72.5714']

    if not end_coords:
        end_coords = ['23.0225, 72.5714']
        
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
            if ws_trucks is not None:
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
            'deliver_bag': bool(getattr(r, 'deliver_bag', False)),
            'customer_status': getattr(r, 'customer_status', 'ACTIVE') or 'ACTIVE',
            'geocode_quality': getattr(r, 'geocode_quality', 'UNKNOWN') or 'UNKNOWN',
            'coord_source': getattr(r, 'coord_source', 'UNKNOWN') or 'UNKNOWN',
            'is_manually_corrected': getattr(r, 'is_manually_corrected', False) or False
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

    # Calculate identical coordinate warnings for 3+ identical geocoded/default stops
    identical_coord_warnings = []
    coord_counts = {}
    for c in customers:
        if c.get('lat') is not None and c.get('lng') is not None:
            pt = (round(c['lat'], 5), round(c['lng'], 5))
            coord_counts.setdefault(pt, []).append(c)

    for pt, grp in coord_counts.items():
        if len(grp) >= 3 and any(x.get('coord_source') in ('GEOCODE', 'DEFAULT') for x in grp):
            names = [x.get('name', 'Stop') for x in grp[:3]]
            identical_coord_warnings.append({
                'lat': pt[0],
                'lng': pt[1],
                'count': len(grp),
                'names': names,
                'message': f"{len(grp)} stops share identical geocoded coordinates ({pt[0]}, {pt[1]}): {', '.join(names)}..."
            })

    return jsonify({
        'customers': customers,
        'identical_coord_warnings': identical_coord_warnings,
        'routes': routes,
        'route_times': route_times,
        'route_distances': route_distances,
        'start_coords': start_coords,
        'end_coords': end_coords,
        'driver_tokens': driver_tokens,
        'drivers': drivers_data,
        'is_from_template': metadata.get('is_from_template') == 'true',
        'current_template_id': metadata.get('current_template_id'),
        'current_template_name': metadata.get('current_template_name'),
        'outlier_warnings': json.loads(metadata.get('outlier_warnings', '[]'))
    })

@app.route('/api/mark_completed/<int:customer_id>', methods=['POST'])
@login_required
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
        driver = verify_auth_token(token)
        if not driver:
            return jsonify({'error': 'Invalid or expired token'}), 401

        if driver.role == 'ADMIN':
            fb_custom_token = None
            try:
                fb_custom_token, _ = create_firebase_custom_token(driver)
            except Exception:
                pass
            return jsonify({
                'is_admin': True,
                'role': 'ADMIN',
                'truck_id': '1',
                'driver_name': driver.name or driver.username,
                'driver_id': driver.id,
                'has_assigned_route': False,
                'assigned_template_id': None,
                'assigned_template_name': None,
                'stop_count': 0,
                'firebase_custom_token': fb_custom_token
            })
        if driver.role == 'DRIVER':
            # Check if this driver currently has an assigned template/route in SQL
            has_assigned_route = False
            assigned_tmpl_name = None
            if driver.assigned_template_id:
                tmpl = db.session.get(SavedTemplate, driver.assigned_template_id)
                if tmpl:
                    has_assigned_route = True
                    assigned_tmpl_name = tmpl.name
            
            # Verify if customers actually exist in DB for this truck
            cust_count = 0
            if driver.truck_id:
                cust_count = Customer.query.filter(Customer.truck_id == driver.truck_id, Customer.id > -1000).count()
                if cust_count == 0:
                    has_assigned_route = False
            else:
                has_assigned_route = False
                
            # If no route is assigned, actively wipe any stale ghost stops in Firebase for this truck
            if not has_assigned_route and driver.truck_id:
                try:
                    id_token = get_firebase_token()
                    if id_token:
                        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
                        requests.delete(f"{firebase_url}/routes/route_{driver.truck_id}.json?auth={id_token}", timeout=3)
                except:
                    pass

            fb_custom_token = None
            try:
                fb_custom_token, _ = create_firebase_custom_token(driver)
            except Exception:
                pass

            return jsonify({
                'truck_id': str(driver.truck_id) if driver.truck_id is not None else None,
                'driver_name': driver.name or driver.username,
                'driver_id': driver.id,
                'has_assigned_route': has_assigned_route,
                'assigned_template_id': driver.assigned_template_id if has_assigned_route else None,
                'assigned_template_name': assigned_tmpl_name,
                'stop_count': cust_count,
                'firebase_custom_token': fb_custom_token
            })
        return jsonify({'error': 'Unauthorized role'}), 403
    except Exception:
        pass
        
    return jsonify({'error': 'Invalid or expired token'}), 401

@app.route('/download_excel')
@any_permission_required('routes.generate_view', 'routes.view')
def download_excel():
    customers = Customer.query.order_by(Customer.truck_id.asc(), Customer.stop_number.asc()).all()
    if not customers: return "No data", 400
    
    def sanitize_formula_injection(val):
        if isinstance(val, str) and len(val) > 0 and val[0] in ('=', '+', '-', '@', '\t', '\r'):
            return f"'{val}"
        return val

    data = [{
        'truck': c.truck_id,
        'stop_number': c.stop_number,
        'name': sanitize_formula_injection(c.name),
        'phone': sanitize_formula_injection(c.phone),
        'address': sanitize_formula_injection(c.address),
        'location_url': sanitize_formula_injection(c.location_url),
        'lat': c.lat,
        'lng': c.lng,
        'status': c.status
    } for c in customers]
    
    df = pd.DataFrame(data)
    export_path = os.path.join(app.config['UPLOAD_FOLDER'], 'optimized_routes.xlsx')
    df.to_excel(export_path, index=False)
    
    return send_file(export_path, as_attachment=True)

@app.route('/api/remove_stop', methods=['POST'])
@permission_required('routes.edit')
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
        try:
            db.session.rollback()
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_stop', methods=['POST'])
@permission_required('routes.edit')
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
    
    # Auto-detect if user pasted a map link into the address input
    if not location_url and address and ('http://' in str(address) or 'https://' in str(address) or 'maps.app.goo.gl' in str(address)):
        location_url = address
        address = ''

    # 1. Direct coordinate extraction if user typed or pasted raw coordinates
    if lat is None or lng is None:
        for candidate in [location_url, address]:
            if candidate and isinstance(candidate, str):
                c_lat, c_lng = extract_lat_lng(candidate)
                if c_lat is not None and c_lng is not None and (8.0 <= c_lat <= 38.0) and (68.0 <= c_lng <= 98.0):
                    lat, lng = c_lat, c_lng
                    break

    # 2. Extract from Google Maps URL (or shortlink)
    if lat is None or lng is None:
        if location_url:
            url_match = re.search(r'(https?://[^\s]+)', str(location_url))
            if url_match:
                lat, lng = resolve_gmaps_url(url_match.group(1))
            
    if lat is None and isinstance(lng, str):
        address = lng
        lng = None
        
    geocode_quality = 'UNKNOWN'
    coord_source = 'UNKNOWN'
    if (lat is None or lng is None) and address:
        glat, glng, gqual = geocode_address_robust(str(address))
        if glat is not None and glng is not None:
            lat, lng = glat, glng
            geocode_quality = gqual
            coord_source = 'GEOCODE'
    elif lat is not None and lng is not None:
        geocode_quality = 'EXACT'
        coord_source = 'MANUAL'
        
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
                confirmation='NOT_CONFIRMED', customer_status='ACTIVE',
                geocode_quality=geocode_quality, coord_source=coord_source,
                is_manually_corrected=True
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
                    "deliver_bag": False,
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
                confirmation='NOT_CONFIRMED', customer_status='ACTIVE',
                geocode_quality=geocode_quality, coord_source=coord_source,
                is_manually_corrected=True
            )
            db.session.add(new_cust)
            db.session.commit()
            recompute_route_metrics()
            return jsonify({'success': True, 'customer_id': new_id})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
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




@app.route('/api/ai_rebalance', methods=['POST'])
@permission_required('routes.edit')
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
        if isinstance(original_starts[i], str):
            slat, slng = map(float, original_starts[i].split(','))
        elif isinstance(original_starts[i], (list, tuple)):
            slat, slng = float(original_starts[i][0]), float(original_starts[i][1])
        else:
            slat, slng = 23.0225, 72.5714
            
        lat, lng = slat, slng
        
        # Override with live GPS if available and truck is not offline
        if truck_id_str in trucks_data:
            t = trucks_data[truck_id_str]
            if t.get('currentLat') and t.get('currentLng'): # Always use their last known position
                lat = float(t['currentLat'])
                lng = float(t['currentLng'])
                
        start_coords.append((lat, lng))
        
        if original_ends and len(original_ends) > i:
            end_val = original_ends[i]
        elif original_ends:
            end_val = original_ends[0]
        else:
            end_val = (lat, lng)
            
        if isinstance(end_val, str):
            elat, elng = map(float, end_val.split(','))
        elif isinstance(end_val, (list, tuple)):
            elat, elng = float(end_val[0]), float(end_val[1])
        else:
            elat, elng = lat, lng
        end_coords.append((elat, elng))
            
    # 4. Get all PENDING stops (exclude Depot -1000)
    pending_customers = Customer.query.filter(Customer.status == 'PENDING', Customer.id > -1000).all()
    if not pending_customers:
        return jsonify({'error': 'No pending stops to rebalance'}), 400
        
    customers_data = [{
        'id': c.id, 'name': c.name, 'phone': c.phone, 'address': c.address,
        'location_url': c.location_url, 'lat': c.lat, 'lng': c.lng
    } for c in pending_customers if not (c.confirmation == 'CANCELLED' and not getattr(c, 'deliver_bag', False))]
    
    cancelled_customers = [c for c in pending_customers if c.confirmation == 'CANCELLED' and not getattr(c, 'deliver_bag', False)]
    cancelled_by_truck = {}
    for c in cancelled_customers:
        tid = c.truck_id or 1
        if tid not in cancelled_by_truck: cancelled_by_truck[tid] = []
        cancelled_by_truck[tid].append(c)
    
    # 5. Run AI
    valid_customers_data = [c for c in customers_data if c.get('lat') is not None and c.get('lng') is not None and c.get('geocode_quality') != 'FAILED']
    aco = ACO_VRP(start_coords, end_coords, valid_customers_data, num_trucks=num_trucks)
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
                        "deliver_bag": bool(getattr(c, "deliver_bag", False)),
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
                    "deliver_bag": bool(getattr(c, "deliver_bag", False)),
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
                "deliver_bag": bool(getattr(c, "deliver_bag", False)),
                "customer_status": getattr(c, "customer_status", "ACTIVE") or "ACTIVE"
            }

    # 7. Push to Firebase
    requests.delete(f"{firebase_url}/routes.json?auth={id_token}")
    for route_key, stops in routes_payload.items():
        requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops})
        
    recompute_route_metrics()
    return jsonify({'success': True})

@app.route('/api/update_route_manual', methods=['POST'])
@permission_required('routes.edit')
def update_route_manual():
    try:
        data = (request.json or {}).get('routes', {})
        
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
                        "deliver_bag": bool(getattr(c, "deliver_bag", False)),
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
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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


@app.route('/api/update_customer_details', methods=['POST'])
@permission_required('routes.edit')
def update_customer_details():
    data = request.json or {}
    cust_id = data.get('id')
    if not cust_id:
        return jsonify({'error': 'Customer ID is required'}), 400
        
    try:
        cust_id = int(cust_id)
    except:
        return jsonify({'error': 'Invalid customer id'}), 400
        
    c = db.session.get(Customer, cust_id)
    if not c:
        return jsonify({'error': 'Customer not found'}), 404
        
    name = data.get('name')
    if name:
        c.name = str(name).strip()
        
    if 'phone' in data:
        c.phone = str(data.get('phone') or '').strip()
        
    if 'address' in data:
        c.address = str(data.get('address') or '').strip()
        
    if 'customer_status' in data and data.get('customer_status'):
        c.customer_status = data.get('customer_status')
        
    if 'confirmation' in data and data.get('confirmation'):
        c.confirmation = data.get('confirmation')

    if 'deliver_bag' in data:
        c.deliver_bag = bool(data.get('deliver_bag'))

    if 'truck_id' in data and data.get('truck_id') is not None:
        try:
            c.truck_id = int(data.get('truck_id'))
        except:
            pass

    if 'stop_number' in data and data.get('stop_number') is not None:
        try:
            c.stop_number = int(data.get('stop_number'))
        except:
            pass
        
    location_url = data.get('location_url')
    if location_url is not None:
        loc_str = str(location_url).strip()
        c.location_url = loc_str
        if loc_str:
            c_lat, c_lng = extract_lat_lng(loc_str)
            if c_lat is not None and c_lng is not None and (8.0 <= c_lat <= 38.0) and (68.0 <= c_lng <= 98.0):
                c.lat, c.lng = c_lat, c_lng
            else:
                url_match = re.search(r'(https?://[^\s]+)', loc_str)
                if url_match:
                    res_lat, res_lng = resolve_gmaps_url(url_match.group(1))
                    if res_lat is not None and res_lng is not None:
                        c.lat, c.lng = res_lat, res_lng

    if 'lat' in data and 'lng' in data and data.get('lat') is not None and data.get('lng') is not None:
        try:
            c.lat = float(data.get('lat'))
            c.lng = float(data.get('lng'))
            c.is_manually_corrected = True
            c.coord_source = 'MANUAL'
            c.geocode_quality = 'EXACT'
        except:
            pass
            
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'DB Error: {str(e)}'}), 500

    # Also update matching customer in current template's JSON if currently editing a template
    curr_tmpl_meta = Metadata.query.filter_by(key='current_template_id').first()
    if curr_tmpl_meta and curr_tmpl_meta.value:
        try:
            t = db.session.get(SavedTemplate, int(curr_tmpl_meta.value))
            if t and t.customers_json:
                t_custs = json.loads(t.customers_json or '[]')
                updated_tmpl = False
                for tc in t_custs:
                    if str(tc.get('id')) == str(c.id):
                        tc['name'] = c.name
                        tc['phone'] = c.phone or ''
                        tc['address'] = c.address or ''
                        tc['location_url'] = c.location_url or ''
                        if c.lat is not None:
                            tc['lat'] = c.lat
                            tc['geocode_quality'] = 'EXACT'
                            tc['coord_source'] = 'MANUAL'
                            tc['is_manually_corrected'] = True
                        if c.lng is not None:
                            tc['lng'] = c.lng
                            tc['geocode_quality'] = 'EXACT'
                            tc['coord_source'] = 'MANUAL'
                            tc['is_manually_corrected'] = True
                        tc['customer_status'] = c.customer_status
                        tc['confirmation'] = c.confirmation
                        tc['deliver_bag'] = bool(getattr(c, 'deliver_bag', False))
                        if c.truck_id is not None:
                            tc['truck_id'] = c.truck_id
                        if c.stop_number is not None:
                            tc['stop_number'] = c.stop_number
                        updated_tmpl = True
                        break
                if updated_tmpl:
                    t.customers_json = json.dumps(t_custs)
                    db.session.commit()
        except Exception as tmpl_e:
            print("Template JSON sync error in update_customer_details:", tmpl_e)

    # Sync with Firebase if on an assigned truck
    if c.truck_id and c.stop_number:
        try:
            import requests
            firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
            id_token = get_firebase_token()
            if id_token:
                payload = {
                    "name": c.name,
                    "phone": c.phone or "",
                    "address": c.address or "",
                    "customer_status": c.customer_status or "ACTIVE",
                    "confirmation": c.confirmation or "NOT_CONFIRMED",
                    "deliver_bag": bool(getattr(c, "deliver_bag", False)),
                    "sequence": c.stop_number
                }
                if c.lat is not None and c.lng is not None:
                    payload["lat"] = c.lat
                    payload["lng"] = c.lng
                requests.patch(f"{firebase_url}/routes/route_{c.truck_id}/stops/{c.id}.json?auth={id_token}", json=payload)
        except Exception as e:
            print("Firebase sync error in update_customer_details:", e)
            
    try:
        recompute_route_metrics()
    except:
        pass
        
    return jsonify({
        'success': True,
        'customer': {
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'address': c.address,
            'location_url': c.location_url,
            'lat': c.lat,
            'lng': c.lng,
            'customer_status': c.customer_status,
            'confirmation': c.confirmation,
            'deliver_bag': bool(getattr(c, 'deliver_bag', False))
        }
    })

@app.route('/api/assign_route', methods=['POST'])
@permission_required('routes.assign_driver')
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
    
    if requested_truck_id:
        try:
            truck_id_int = int(requested_truck_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid truck_id'}), 400

        if driver.truck_id != truck_id_int:
            with assignment_coordination_guard():
                old_truck_id = driver.truck_id
                colliding = User.query.filter(User.role == 'DRIVER', User.truck_id == truck_id_int, User.id != driver.id).all()

                # Monotonic revision and generation allocation
                c_revs = {}
                for c in colliding:
                    if not c.generation_id:
                        c.generation_id = uuid.uuid4().hex
                    c_revs[c.id] = allocate_next_assignment_revision()
                if not driver.generation_id:
                    driver.generation_id = uuid.uuid4().hex
                d_rev = allocate_next_assignment_revision()

                # Track all affected drivers and their original truck IDs for rollback recovery
                affected_drivers = {}
                for c in colliding:
                    affected_drivers[str(c.id)] = {
                        'old_truck': c.truck_id,
                        'target_truck': None,
                        'action': 'REVOKE',
                        'generation_id': c.generation_id,
                        'revision': c_revs[c.id]
                    }
                if old_truck_id and old_truck_id != truck_id_int:
                    affected_drivers[str(driver.id)] = {
                        'old_truck': old_truck_id,
                        'target_truck': truck_id_int,
                        'action': 'GRANT',
                        'generation_id': driver.generation_id,
                        'revision': d_rev
                    }
                elif not old_truck_id:
                    affected_drivers[str(driver.id)] = {
                        'old_truck': None,
                        'target_truck': truck_id_int,
                        'action': 'GRANT',
                        'generation_id': driver.generation_id,
                        'revision': d_rev
                    }

                op_id = uuid.uuid4().hex

                # STEP 1: Durable intent persistence in SQLite BEFORE first Firebase mutation
                stage_ok, stage_err = stage_assignment_intent(op_id, 'ASSIGN_ROUTE', affected_drivers, commit=True)
                if not stage_ok:
                    return jsonify({'success': False, 'error': f"Failed to stage assignment intent: {stage_err}"}), 500

                # STEP 2: Pre-revocation in RTDB
                for c in colliding:
                    c_ok, c_err = set_driver_rtdb_assignment(c.id, None)
                    if not c_ok:
                        update_assignment_intent_status(op_id, 'FAILED', last_error=c_err)
                        return jsonify({'success': False, 'error': f"Failed to pre-revoke colliding driver {c.id}: {c_err}"}), 502

                if old_truck_id and old_truck_id != truck_id_int:
                    old_ok, old_err = set_driver_rtdb_assignment(driver.id, None)
                    if not old_ok:
                        update_assignment_intent_status(op_id, 'FAILED', last_error=old_err)
                        return jsonify({'success': False, 'error': f"Failed to pre-revoke previous assignment for driver {driver.id}: {old_err}"}), 502

                update_assignment_intent_status(op_id, 'REVOKED', commit=False)

                # STEP 3: SQLite modification & commit
                for c in colliding:
                    c.truck_id = None
                    c.assigned_template_id = None
                    c.assignment_revision = c_revs[c.id]

                driver.truck_id = truck_id_int
                driver.assignment_revision = d_rev

                update_assignment_intent_status(op_id, 'COMMITTED', commit=False)
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    restore_errors = []
                    for aff_id_str, aff_info in affected_drivers.items():
                        aff_id = int(aff_id_str)
                        aff_truck = aff_info.get('old_truck')
                        r_ok, r_err = set_driver_rtdb_assignment(aff_id, aff_truck)
                        if not r_ok:
                            record_pending_rtdb_assignment(
                                aff_id, aff_truck, last_error=r_err, commit=True, op_id=op_id,
                                generation_id=aff_info.get('generation_id'), revision=aff_info.get('revision')
                            )
                            restore_errors.append(f"Driver {aff_id}: {r_err}")

                    err_msg = f"Database commit failed: {str(e)}."
                    if restore_errors:
                        err_msg += f" Firebase restoration failed for {', '.join(restore_errors)}. Outbox recovery queued."
                    else:
                        err_msg += " Pre-revoked live tracking assignments restored."
                    return jsonify({
                        'success': False,
                        'error': err_msg,
                        'pending_sync_recorded': bool(restore_errors)
                    }), 500

                # STEP 4: RTDB Grant
                grant_ok, grant_err = set_driver_rtdb_assignment(driver.id, truck_id_int)
                if not grant_ok:
                    rec_ok, rec_err = record_pending_rtdb_assignment(
                        driver.id, truck_id_int, last_error=grant_err, commit=True, op_id=op_id,
                        generation_id=driver.generation_id, revision=d_rev, action='GRANT'
                    )
                    for c in colliding:
                        complete_assignment_intent(op_id, driver_id=c.id, generation_id=c.generation_id, revision=c_revs[c.id], commit=True)
                    return jsonify({
                        'success': False,
                        'error': f"Driver assignment committed to database, but Firebase RTDB sync failed: {grant_err}",
                        'pending_sync_recorded': rec_ok
                    }), 502
                else:
                    complete_assignment_intent(op_id, commit=True)
    elif not driver.truck_id:
        return jsonify({'error': 'Driver is unassigned. Please specify a truck_id to assign a route.'}), 400
        
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
    db.session.flush()
    
    import json
    cust_list = json.loads(t.customers_json or '[]')
    
    existing_ids = set(r[0] for r in db.session.query(Customer.id).all())
    max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
    if max_id < 0:
        max_id = 0
    max_id_tracker = [max_id]

    for c in cust_list:
        raw_id = int(c['id'])
        is_depot = (raw_id <= -1000 or c.get('name') == 'End Location / Depot')
        cid = allocate_customer_id(raw_id, is_depot, driver.truck_id, existing_ids, max_id_tracker)
        new_cust = Customer(
            id=cid, name=c['name'], phone=c.get('phone'), address=c.get('address'),
            location_url=c.get('location_url'), lat=c.get('lat'), lng=c.get('lng'),
            status='PENDING', truck_id=driver.truck_id, stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
            deliver_bag=bool(c.get('deliver_bag', False)),
            customer_status=c.get('customer_status', 'ACTIVE'),
            geocode_quality=c.get('geocode_quality', 'UNKNOWN'),
            coord_source=c.get('coord_source', 'UNKNOWN'),
            is_manually_corrected=c.get('is_manually_corrected', False),
            master_customer_id=c.get('master_customer_id') or (raw_id if raw_id > 0 and raw_id < 1000000 else None)
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
                        "deliver_bag": bool(getattr(c, 'deliver_bag', False)),
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
@any_permission_required('templates.create', 'templates.edit', 'routes.generate_save_template')
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
        'deliver_bag': bool(getattr(c, 'deliver_bag', False)),
        'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE',
        'geocode_quality': getattr(c, 'geocode_quality', 'UNKNOWN') or 'UNKNOWN',
        'coord_source': getattr(c, 'coord_source', 'UNKNOWN') or 'UNKNOWN',
        'is_manually_corrected': getattr(c, 'is_manually_corrected', False) or False,
        'master_customer_id': getattr(c, 'master_customer_id', None)
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
                max_id_tracker = [max_id]
                    
                for c in cust_list:
                    raw_id = int(c['id'])
                    is_depot = (raw_id <= -1000 or c.get('name') == 'End Location / Depot')
                    cid = allocate_customer_id(raw_id, is_depot, d.truck_id, existing_ids, max_id_tracker)
                    new_cust = Customer(
                        id=cid, name=c['name'], phone=c.get('phone'), address=c.get('address'),
                        location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
                        status=c.get('status', 'PENDING'), truck_id=d.truck_id, stop_number=c.get('stop_number'),
                        confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
                        deliver_bag=bool(c.get('deliver_bag', False)),
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
                                    "deliver_bag": bool(getattr(c, 'deliver_bag', False)),
                                    "customer_status": getattr(c, 'customer_status', 'ACTIVE')
                                }
                            requests.put(f"{firebase_url}/routes/{route_key}.json?auth={id_token}", json={"stops": stops_payload})
                    except Exception as e:
                        print("Firebase sync error on template save:", e)
            recompute_route_metrics()
    
    return jsonify({'success': True})

@app.route('/api/templates', methods=['GET'])
@permission_required('templates.view')
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
@permission_required('routes.view')
def get_assigned_routes():
    # Sync latest completion statuses from Firebase
    try:
        sync_firebase_to_sql()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print("sync_firebase_to_sql error in get_assigned_routes:", e)

    try:
        drivers = User.query.filter(User.assigned_template_id != None, User.truck_id != None).all()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
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
                db.session.flush()
                existing_ids = set(r[0] for r in db.session.query(Customer.id).all())
                max_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
                if max_id < 0:
                    max_id = 0
                max_id_tracker = [max_id]
                for c in t_custs:
                    raw_id = int(c['id'])
                    is_depot = (raw_id <= -1000 or c.get('name') == 'End Location / Depot')
                    cid = allocate_customer_id(raw_id, is_depot, d.truck_id, existing_ids, max_id_tracker)
                    new_cust = Customer(
                        id=cid, name=c['name'], phone=c.get('phone'), address=c.get('address'),
                        location_url=c.get('location_url'), lat=c['lat'], lng=c['lng'],
                        status=c.get('status', 'PENDING'), truck_id=d.truck_id, stop_number=c.get('stop_number'),
                        confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
                        deliver_bag=bool(c.get('deliver_bag', False)),
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
@permission_required('routes.delete')
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
            
    # Also explicitly clear Customer records for truck_id if provided directly
    if truck_id:
        try:
            Customer.query.filter_by(truck_id=int(truck_id)).delete()
        except:
            pass
            
    db.session.commit()
    
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
        if id_token:
            trucks_to_clear = set()
            if truck_id:
                try: trucks_to_clear.add(int(truck_id))
                except: pass
            for d in drivers:
                if d.truck_id:
                    trucks_to_clear.add(d.truck_id)
            for tid in trucks_to_clear:
                requests.delete(f"{firebase_url}/routes/route_{tid}.json?auth={id_token}")
                requests.patch(f"{firebase_url}/trucks/{tid}.json?auth={id_token}", json={
                    "driverName": None,
                    "driverId": None,
                    "status": "offline",
                    "routeCompleted": False
                })
    except Exception as e:
        print("Firebase unassign error:", e)
        
    recompute_route_metrics()
    return jsonify({'success': True})

@app.route('/api/mark_stop_status', methods=['POST'])
def mark_stop_status():
    """
    Direct high-priority endpoint for the driver app to report stop completion / skip.
    Updates the SQL database and immediately pushes to Firebase Realtime Database
    over REST, ensuring zero-delay updates even if the driver's WebSocket was idle.
    """
    data = request.json or {}
    truck_id = data.get('truck_id')
    driver_id = data.get('driver_id')
    stop_id = data.get('stop_id')
    status = (data.get('status') or 'COMPLETED').upper()
    updates = data.get('updates') or {}

    VALID_STOP_STATUSES = {'COMPLETED', 'SKIPPED', 'PENDING'}
    if status not in VALID_STOP_STATUSES:
        return jsonify({'error': f"Invalid stop status '{status}'. Valid statuses: {sorted(list(VALID_STOP_STATUSES))}"}), 400

    # Authenticate caller
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
    token = token or request.headers.get('X-Driver-Token') or request.args.get('token') or (str(driver_id) if driver_id else None)
    
    caller = None
    if token:
        caller = verify_auth_token(token)
    elif session.get('user_id'):
        caller = db.session.get(User, session.get('user_id'))

    if not caller:
        return jsonify({'error': 'Unauthorized: Valid driver or admin authentication required'}), 401

    if caller.role != 'ADMIN' and truck_id and caller.truck_id and int(caller.truck_id) != int(truck_id):
        return jsonify({'error': 'Forbidden: Driver is not assigned to this truck'}), 403
    
    stop_ids_to_update = set()
    if stop_id:
        try:
            stop_ids_to_update.add(int(stop_id))
        except:
            pass
            
    for k, v in updates.items():
        if '/status' in k:
            sid_str = k.split('/')[0]
            try:
                stop_ids_to_update.add(int(sid_str))
            except:
                pass
                
    if stop_ids_to_update:
        q = Customer.query.filter(Customer.id.in_(list(stop_ids_to_update)))
        if caller.role != 'ADMIN' and truck_id:
            q = q.filter(Customer.truck_id == int(truck_id))
        q.update({'status': status}, synchronize_session=False)
        db.session.commit()
        
    now_ms = int(time.time() * 1000)
    try:
        import requests
        firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
        id_token = get_firebase_token()
        if id_token and truck_id:
            fb_patch = {}
            for sid in stop_ids_to_update:
                fb_patch[f"{sid}/status"] = status
            if fb_patch:
                requests.patch(
                    f"{firebase_url}/routes/route_{truck_id}/stops.json?auth={id_token}",
                    json=fb_patch,
                    timeout=5
                )
            touch = {
                "lastUpdated": now_ms,
                "lastStopAction": now_ms
            }
            requests.patch(f"{firebase_url}/trucks/{truck_id}.json?auth={id_token}", json=touch, timeout=4)
            if driver_id:
                requests.patch(f"{firebase_url}/driver_locations/{driver_id}.json?auth={id_token}", json=touch, timeout=4)
    except Exception as e:
        print("mark_stop_status Firebase sync error:", e)
        
    return jsonify({'success': True, 'updated': list(stop_ids_to_update), 'status': status})


@app.route('/api/live_route_sync')
def live_route_sync():
    custs = Customer.query.filter(Customer.truck_id != None, Customer.id > -1000).all()
    routes = {}
    for c in custs:
        rk = f"route_{c.truck_id}"
        if rk not in routes:
            routes[rk] = {"stops": {}}
        routes[rk]["stops"][str(c.id)] = {
            "id": c.id,
            "status": c.status or "PENDING",
            "confirmation": c.confirmation or "NOT_CONFIRMED",
            "deliver_bag": bool(getattr(c, "deliver_bag", False)),
            "sequence": c.stop_number,
            "name": c.name,
            "customer_status": c.customer_status or "ACTIVE",
            "lat": c.lat,
            "lng": c.lng
        }
    return jsonify({'success': True, 'routes': routes})


@app.route('/api/driver/telemetry_sync', methods=['POST'])
def driver_telemetry_sync():
    """
    Durable offline GPS telemetry synchronization endpoint.
    Receives batched GPS records collected while offline or live.
    Guarantees:
    1. Caller authentication (driver or admin).
    2. Idempotency via unique event_id deduplication.
    3. Coordinate sanity validation (bounds check [-90,90], [-180,180], reject Null Island).
    4. Durable storage in TruckTelemetryHistory.
    5. Strict Ordering Rule: Firebase RTDB /trucks/{truck_id} live position is only updated
       if the batch's newest capture_time is >= the current live position timestamp in RTDB.
       Historical offline backlogs will never overwrite a more recent live position.
    """
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
    token = token or request.headers.get('X-Driver-Token') or request.args.get('token')
    
    caller = None
    if token:
        caller = verify_auth_token(token)
    elif session.get('user_id'):
        caller = db.session.get(User, session.get('user_id'))
        
    if not caller or not getattr(caller, 'is_active', True):
        return jsonify({'error': 'Unauthorized: Valid active driver or admin token required'}), 401

    payload = request.get_json(silent=True) or {}
    records = payload.get('records', [])
    if not isinstance(records, list):
        return jsonify({'error': 'Invalid payload format: records must be an array'}), 400

    if not records:
        return jsonify({'success': True, 'synced_count': 0, 'deduplicated_count': 0, 'rejected_count': 0, 'total_received': 0})

    saved_count = 0
    duplicate_count = 0
    rejected_count = 0
    truck_latest_fixes = {}

    batch_event_ids = [str(r.get('event_id')).strip() for r in records if r.get('event_id')]
    existing_ids = set()
    if batch_event_ids:
        try:
            found = db.session.query(TruckTelemetryHistory.event_id).filter(TruckTelemetryHistory.event_id.in_(batch_event_ids)).all()
            existing_ids = {row[0] for row in found}
        except Exception as e:
            app.logger.warning(f"Error querying existing event_ids: {e}")

    new_entities = []

    for r in records:
        if not isinstance(r, dict):
            rejected_count += 1
            continue

        event_id = str(r.get('event_id') or '').strip()
        if not event_id:
            event_id = str(uuid.uuid4())

        if event_id in existing_ids:
            duplicate_count += 1
            continue

        try:
            lat = float(r.get('latitude', 0.0))
            lng = float(r.get('longitude', 0.0))
        except (ValueError, TypeError):
            rejected_count += 1
            continue

        # Coordinate bounds and Null Island validation
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            rejected_count += 1
            continue
        if abs(lat) < 0.0001 and abs(lng) < 0.0001:
            rejected_count += 1
            continue

        # Truck assignment authorization check
        raw_truck_id = r.get('truck_id')
        try:
            record_truck_id = int(raw_truck_id) if raw_truck_id is not None and str(raw_truck_id).strip() != '' else None
        except (ValueError, TypeError):
            record_truck_id = None

        if caller.role != 'ADMIN':
            assigned_truck = caller.truck_id
            if assigned_truck is not None and record_truck_id is not None and int(record_truck_id) != int(assigned_truck):
                rejected_count += 1
                continue
            if record_truck_id is None and assigned_truck is not None:
                record_truck_id = int(assigned_truck)

        if record_truck_id is None:
            rejected_count += 1
            continue

        driver_id_val = caller.id
        if caller.role == 'ADMIN' and r.get('driver_id'):
            try:
                driver_id_val = int(r.get('driver_id'))
            except (ValueError, TypeError):
                driver_id_val = caller.id

        capture_time = r.get('capture_time')
        try:
            capture_time = int(capture_time) if capture_time else int(time.time() * 1000)
        except (ValueError, TypeError):
            capture_time = int(time.time() * 1000)

        speed_val = None
        if r.get('speed') is not None:
            try: speed_val = float(r.get('speed'))
            except (ValueError, TypeError): pass

        bearing_val = None
        if r.get('bearing') is not None:
            try: bearing_val = float(r.get('bearing'))
            except (ValueError, TypeError): pass

        accuracy_val = None
        if r.get('accuracy') is not None:
            try: accuracy_val = float(r.get('accuracy'))
            except (ValueError, TypeError): pass

        seq_val = None
        if r.get('sequence_number') is not None:
            try: seq_val = int(r.get('sequence_number'))
            except (ValueError, TypeError): pass

        entity = TruckTelemetryHistory(
            event_id=event_id,
            driver_id=driver_id_val,
            truck_id=record_truck_id,
            assignment_id=str(r.get('assignment_id') or ''),
            latitude=lat,
            longitude=lng,
            accuracy=accuracy_val,
            speed=speed_val,
            bearing=bearing_val,
            provider=str(r.get('provider') or 'fused')[:32],
            capture_time=capture_time,
            sequence_number=seq_val
        )
        new_entities.append(entity)
        existing_ids.add(event_id)
        saved_count += 1

        # Track latest fix per truck in this batch
        if record_truck_id not in truck_latest_fixes or capture_time > truck_latest_fixes[record_truck_id]['capture_time']:
            truck_latest_fixes[record_truck_id] = {
                'latitude': lat,
                'longitude': lng,
                'accuracy': accuracy_val,
                'speed': speed_val,
                'bearing': bearing_val,
                'capture_time': capture_time,
                'driver_id': driver_id_val
            }

    if new_entities:
        try:
            db.session.bulk_save_objects(new_entities)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error persisting telemetry batch: {e}")
            return jsonify({'error': 'Database error persisting telemetry'}), 500

    # Strict Ordering Update for Firebase RTDB
    firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
    id_token = get_firebase_token()
    if id_token and truck_latest_fixes:
        for tid, latest_fix in truck_latest_fixes.items():
            try:
                t_resp = requests.get(f"{firebase_url}/trucks/{tid}.json?auth={id_token}", timeout=3)
                existing_ts = 0
                if t_resp.status_code == 200 and t_resp.json():
                    t_data = t_resp.json()
                    existing_ts = int(t_data.get('timestamp') or 0)

                # Strict Ordering Rule:
                # Only update live position if latest fix in batch is >= current live timestamp
                if latest_fix['capture_time'] >= existing_ts:
                    now_ms = time.time() * 1000
                    status_str = "online" if (now_ms - latest_fix['capture_time']) < 120000 else "offline"
                    patch_payload = {
                        "currentLat": latest_fix['latitude'],
                        "currentLng": latest_fix['longitude'],
                        "speed": latest_fix['speed'] or 0.0,
                        "heading": latest_fix['bearing'] or 0.0,
                        "accuracy": latest_fix['accuracy'] or 0.0,
                        "timestamp": latest_fix['capture_time'],
                        "lastUpdated": datetime.datetime.fromtimestamp(latest_fix['capture_time'] / 1000.0, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                        "status": status_str
                    }
                    requests.patch(f"{firebase_url}/trucks/{tid}.json?auth={id_token}", json=patch_payload, timeout=3)
                    
                    if latest_fix.get('driver_id'):
                        requests.patch(f"{firebase_url}/driver_locations/{latest_fix['driver_id']}.json?auth={id_token}", json=patch_payload, timeout=3)
                else:
                    app.logger.info(f"[TELEMETRY SYNC] Truck {tid}: batch capture_time ({latest_fix['capture_time']}) is older than existing live timestamp ({existing_ts}). Live marker NOT overwritten.")
            except Exception as fb_err:
                app.logger.warning(f"[TELEMETRY SYNC] Failed to update Firebase for truck {tid}: {fb_err}")

    return jsonify({
        'success': True,
        'synced_count': saved_count,
        'deduplicated_count': duplicate_count,
        'rejected_count': rejected_count,
        'total_received': len(records)
    })


@app.route('/api/truck_telemetry/<int:truck_id>', methods=['GET'])
def get_truck_telemetry(truck_id):
    """
    Returns recent telemetry breadcrumb points for a given truck.
    Used by Admin Live Tracking dashboard for route trails and audit history.
    """
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
    token = token or request.headers.get('X-Driver-Token') or request.args.get('token')
    
    caller = None
    if token:
        caller = verify_auth_token(token)
    elif session.get('user_id'):
        caller = db.session.get(User, session.get('user_id'))
        
    if not caller or not getattr(caller, 'is_active', True):
        return jsonify({'error': 'Unauthorized: Valid active driver or admin token required'}), 401

    if caller.role != 'ADMIN' and caller.truck_id and int(caller.truck_id) != int(truck_id):
        return jsonify({'error': 'Forbidden: Access limited to assigned truck'}), 403

    limit = min(int(request.args.get('limit', 200)), 1000)
    since_ts = request.args.get('since', type=int)

    query = TruckTelemetryHistory.query.filter_by(truck_id=truck_id)
    if since_ts:
        query = query.filter(TruckTelemetryHistory.capture_time >= since_ts)
    
    records = query.order_by(TruckTelemetryHistory.capture_time.desc()).limit(limit).all()
    records.reverse()

    return jsonify({
        'success': True,
        'truck_id': truck_id,
        'count': len(records),
        'telemetry': [r.to_dict() for r in records]
    })


@app.route('/api/driver_finish_route', methods=['POST'])
def driver_finish_route():
    data = request.json or {}
    truck_id = data.get('truck_id')
    driver_id = data.get('driver_id')
    
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
    token = token or request.headers.get('X-Driver-Token') or request.args.get('token')
    
    driver = None
    if token:
        driver = verify_auth_token(token)
    elif session.get('user_id'):
        driver = db.session.get(User, session.get('user_id'))
            
    if not driver:
        return jsonify({'error': 'Unauthorized: Valid driver credentials required'}), 401

    if driver.role != 'ADMIN' and truck_id and driver.truck_id and int(driver.truck_id) != int(truck_id):
        return jsonify({'error': 'Forbidden: Driver is not assigned to this truck'}), 403
        
    if driver:
        eff_truck_id = driver.truck_id or truck_id
        # Guard: sync latest stop statuses from Firebase and refuse to wipe a route that still has pending actionable stops
        if eff_truck_id:
            try:
                sync_firebase_to_sql()
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
            try:
                truck_stops = Customer.query.filter(
                    Customer.truck_id == int(eff_truck_id),
                    Customer.id > -1000
                ).all()
                pending_actionable = [
                    c for c in truck_stops
                    if (c.status or 'PENDING') == 'PENDING'
                    and not (c.confirmation == 'CANCELLED' and not getattr(c, 'deliver_bag', False))
                ]
                if len(pending_actionable) > 0:
                    return jsonify({
                        'success': False,
                        'error': f'Route still has {len(pending_actionable)} pending stops'
                    }), 400
            except Exception as guard_e:
                print("driver_finish_route guard check error:", guard_e)

        if driver.assigned_template_id:
            old_inst = db.session.get(SavedTemplate, driver.assigned_template_id)
            if old_inst and getattr(old_inst, 'is_assigned_instance', False):
                db.session.delete(old_inst)
        driver.assigned_template_id = None
        
        # Clean up Customer table for this truck so it doesn't linger
        if eff_truck_id:
            try:
                Customer.query.filter_by(truck_id=int(eff_truck_id)).delete()
            except:
                pass
        db.session.commit()
        
        # Clean up Firebase route so next login doesn't see old finished route
        try:
            if eff_truck_id:
                id_token = get_firebase_token()
                if id_token:
                    firebase_url = "https://wasteroutelive-default-rtdb.firebaseio.com"
                    requests.delete(f"{firebase_url}/routes/route_{eff_truck_id}.json?auth={id_token}")
                    requests.patch(f"{firebase_url}/trucks/{eff_truck_id}.json?auth={id_token}", json={
                        "status": "offline",
                        "routeCompleted": True
                    })
        except Exception as e:
            print("driver_finish_route Firebase cleanup error:", e)
            
        return jsonify({'success': True})
    return jsonify({'error': 'Driver not found'}), 404

@app.route('/api/delete_template/<int:t_id>', methods=['DELETE'])
@permission_required('templates.delete')
def delete_template(t_id):
    t = db.session.get(SavedTemplate, t_id)
    if t:
        User.query.filter_by(assigned_template_id=t_id).update({'assigned_template_id': None})
        db.session.delete(t)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/deploy_template/<int:t_id>', methods=['POST'])
@permission_required('templates.deploy')
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
        Customer.query.filter((Customer.truck_id.is_(None)) | (~Customer.truck_id.in_(list(protected_trucks)))).delete(synchronize_session=False)
    else:
        Customer.query.delete()
    Metadata.query.delete()
    db.session.flush()
    
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
    
    # Clean any leftover customer stops on workspace trucks so old dummy data never lingers
    Customer.query.filter(Customer.truck_id.in_(workspace_trucks)).delete(synchronize_session=False)
    
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
    max_id_tracker = [max_id]
        
    deployed_customers = []
    for c in cust_list:
        orig_tid = int(c.get('truck_id') or 1)
        new_tid = truck_id_map.get(orig_tid, orig_tid)
        raw_id = int(c['id'])
        is_depot = (raw_id <= -1000 or c.get('name') == 'End Location / Depot')
        cid = allocate_customer_id(raw_id, is_depot, new_tid, existing_ids, max_id_tracker)
        
        new_cust = Customer(
            id=cid, name=c['name'], phone=c.get('phone'), address=c.get('address'),
            location_url=c.get('location_url'), lat=c.get('lat'), lng=c.get('lng'),
            status='PENDING', truck_id=new_tid, stop_number=c.get('stop_number'),
            confirmation=c.get('confirmation', 'NOT_CONFIRMED'),
            deliver_bag=bool(c.get('deliver_bag', False)),
            customer_status=c.get('customer_status', 'ACTIVE'),
            geocode_quality=c.get('geocode_quality', 'UNKNOWN'),
            coord_source=c.get('coord_source', 'UNKNOWN'),
            is_manually_corrected=c.get('is_manually_corrected', False),
            master_customer_id=c.get('master_customer_id') or (raw_id if raw_id > 0 and raw_id < 1000000 else None)
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
            'deliver_bag': bool(c.get('deliver_bag', False)),
            'customer_status': c.get('customer_status', 'ACTIVE')
        })
        
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Database error during deploy: {str(e)}'}), 500
    
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
                            "deliver_bag": bool(c.get("deliver_bag", False)),
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

# ============================================================================
# MASTER CUSTOMER LIST & DIRECT SAVED TEMPLATE INTEGRATION ENDPOINTS
# ============================================================================

@app.route('/api/master_customers', methods=['GET'])
@permission_required('customers.view')
def get_master_customers():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'ACTIVE').strip().upper()
    try:
        page = max(int(request.args.get('page', 1)), 1)
        limit = min(max(int(request.args.get('limit', 50)), 1), 200)
    except (ValueError, TypeError):
        page = 1
        limit = 50

    query = MasterCustomer.query
    if status_filter == 'ACTIVE':
        query = query.filter(MasterCustomer.customer_status == 'ACTIVE')
    elif status_filter == 'ARCHIVED':
        query = query.filter(MasterCustomer.customer_status == 'ARCHIVED')

    if q:
        search_term = f"%{q}%"
        query = query.filter(
            db.or_(
                MasterCustomer.name.ilike(search_term),
                MasterCustomer.address.ilike(search_term),
                MasterCustomer.phone.ilike(search_term)
            )
        )

    total = query.count()
    customers = query.order_by(MasterCustomer.id.desc()).offset((page - 1) * limit).limit(limit).all()

    import collections, json
    cust_templates_map = collections.defaultdict(list)
    try:
        master_templates = SavedTemplate.query.filter(
            (SavedTemplate.is_assigned_instance == False) | (SavedTemplate.is_assigned_instance == None)
        ).all()
        for tmpl in master_templates:
            try:
                t_custs = json.loads(tmpl.customers_json or '[]')
                for c in t_custs:
                    cid = c.get('master_customer_id') or c.get('id')
                    if cid and tmpl.name not in cust_templates_map[cid]:
                        cust_templates_map[cid].append(tmpl.name)
            except Exception:
                pass
    except Exception:
        pass

    res = [c.to_dict(templates=cust_templates_map.get(c.id, [])) for c in customers]
    return jsonify({
        'success': True,
        'customers': res,
        'total': total,
        'page': page,
        'limit': limit
    })


@app.route('/api/master_customers', methods=['POST'])
@permission_required('customers.create')
def add_master_customer():
    data = request.json or {}
    name = data.get('name')
    address = data.get('address')
    phone = data.get('phone')
    maps_url = data.get('google_maps_url') or data.get('location_url')
    deliver_bag = bool(data.get('deliver_bag', False))

    is_name_ok, name_res = validate_customer_name(name)
    if not is_name_ok:
        return jsonify({'success': False, 'error': name_res}), 400

    is_addr_ok, addr_res = validate_customer_address(address)
    if not is_addr_ok:
        return jsonify({'success': False, 'error': addr_res}), 400

    is_phone_ok, phone_res = validate_phone_number(phone)
    if not is_phone_ok:
        return jsonify({'success': False, 'error': phone_res}), 400

    is_url_ok, url_res = validate_google_maps_url(maps_url)
    if not is_url_ok:
        return jsonify({'success': False, 'error': url_res}), 400

    lat = data.get('lat')
    lng = data.get('lng')
    is_coords_ok, lat_f, lng_f, coord_err = validate_coordinates(lat, lng)
    if not is_coords_ok:
        return jsonify({'success': False, 'error': coord_err}), 400

    coord_source = 'MANUAL' if (lat_f is not None and lng_f is not None) else 'UNKNOWN'
    geocode_quality = 'EXACT' if (lat_f is not None and lng_f is not None) else 'UNKNOWN'
    if lat_f is None or lng_f is None:
        c_lat, c_lng = extract_coords_from_gmaps_url_fast(url_res)
        if c_lat is not None and c_lng is not None:
            lat_f, lng_f = c_lat, c_lng
            coord_source = 'MAPS_URL'
            geocode_quality = 'EXACT'

    existing = MasterCustomer.query.filter(
        MasterCustomer.customer_status != 'ARCHIVED',
        db.func.lower(MasterCustomer.name) == name_res.lower(),
        db.func.lower(MasterCustomer.address) == addr_res.lower()
    ).first()
    if existing:
        return jsonify({'success': False, 'error': 'Customer with this name and address already exists.'}), 409

    norm_phone = normalize_phone_for_dedup(phone_res)
    if norm_phone:
        existing_phone_dup = MasterCustomer.query.filter(
            MasterCustomer.customer_status != 'ARCHIVED',
            MasterCustomer.phone.isnot(None)
        ).all()
        for ep in existing_phone_dup:
            if normalize_phone_for_dedup(ep.phone) == norm_phone:
                return jsonify({'success': False, 'error': f'Phone number already registered to customer {ep.name} (ID: {ep.id}).'}), 409

    max_master_id = db.session.query(db.func.max(MasterCustomer.id)).scalar() or 0
    max_cust_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
    new_id = max(max_master_id, max_cust_id, 0) + 1

    new_cust = MasterCustomer(
        id=new_id,
        name=name_res,
        address=addr_res,
        phone=phone_res,
        location_url=url_res,
        google_maps_url=url_res,
        lat=lat_f,
        lng=lng_f,
        deliver_bag=deliver_bag,
        customer_status='ACTIVE',
        geocode_quality=geocode_quality,
        coord_source=coord_source,
        is_manually_corrected=(lat_f is not None and lng_f is not None)
    )
    db.session.add(new_cust)
    db.session.commit()

    return jsonify({'success': True, 'customer': new_cust.to_dict()}), 201


@app.route('/api/master_customers/<int:cust_id>', methods=['GET'])
@permission_required('customers.view')
def get_master_customer(cust_id):
    cust = db.session.get(MasterCustomer, cust_id)
    if not cust:
        return jsonify({'success': False, 'error': 'Customer not found'}), 404
    return jsonify({'success': True, 'customer': cust.to_dict()})


@app.route('/api/master_customers/<int:cust_id>', methods=['PUT'])
@permission_required('customers.edit')
def update_master_customer(cust_id):
    cust = db.session.get(MasterCustomer, cust_id)
    if not cust:
        return jsonify({'success': False, 'error': 'Customer not found'}), 404

    data = request.json or {}

    new_name = cust.name
    if 'name' in data:
        is_name_ok, name_res = validate_customer_name(data.get('name'))
        if not is_name_ok:
            return jsonify({'success': False, 'error': name_res}), 400
        new_name = name_res

    new_address = cust.address
    if 'address' in data:
        is_addr_ok, addr_res = validate_customer_address(data.get('address'))
        if not is_addr_ok:
            return jsonify({'success': False, 'error': addr_res}), 400
        new_address = addr_res

    new_phone = cust.phone
    if 'phone' in data:
        raw_p = data.get('phone')
        is_phone_ok, phone_res = validate_phone_number(raw_p)
        if not is_phone_ok:
            return jsonify({'success': False, 'error': phone_res}), 400
        new_phone = phone_res

    new_maps_url = cust.google_maps_url or cust.location_url
    if 'google_maps_url' in data or 'location_url' in data:
        raw_u = data.get('google_maps_url') or data.get('location_url')
        is_url_ok, url_res = validate_google_maps_url(raw_u)
        if not is_url_ok:
            return jsonify({'success': False, 'error': url_res}), 400
        new_maps_url = url_res

    # Coordinates update (preserve existing if not provided)
    if 'lat' in data or 'lng' in data:
        lat_in = data.get('lat') if 'lat' in data else cust.lat
        lng_in = data.get('lng') if 'lng' in data else cust.lng
        is_coords_ok, lat_f, lng_f, coord_err = validate_coordinates(lat_in, lng_in)
        if not is_coords_ok:
            return jsonify({'success': False, 'error': coord_err}), 400
        cust.lat = lat_f
        cust.lng = lng_f
        if lat_f is not None and lng_f is not None:
            cust.is_manually_corrected = True
            cust.geocode_quality = 'EXACT'
            cust.coord_source = 'MANUAL'
    elif new_maps_url and (cust.lat is None or cust.lng is None):
        c_lat, c_lng = extract_coords_from_gmaps_url_fast(new_maps_url)
        if c_lat is not None and c_lng is not None:
            cust.lat = c_lat
            cust.lng = c_lng
            cust.geocode_quality = 'EXACT'
            cust.coord_source = 'MAPS_URL'

    existing = MasterCustomer.query.filter(
        MasterCustomer.id != cust_id,
        MasterCustomer.customer_status != 'ARCHIVED',
        db.func.lower(MasterCustomer.name) == new_name.lower(),
        db.func.lower(MasterCustomer.address) == new_address.lower()
    ).first()
    if existing:
        return jsonify({'success': False, 'error': 'Another customer with this name and address already exists.'}), 409

    if new_phone:
        norm_phone = normalize_phone_for_dedup(new_phone)
        if norm_phone:
            existing_phone_dup = MasterCustomer.query.filter(
                MasterCustomer.id != cust_id,
                MasterCustomer.customer_status != 'ARCHIVED',
                MasterCustomer.phone.isnot(None)
            ).all()
            for ep in existing_phone_dup:
                if normalize_phone_for_dedup(ep.phone) == norm_phone:
                    return jsonify({'success': False, 'error': f'Phone number already registered to another customer: {ep.name} (ID: {ep.id}).'}), 409

    cust.name = new_name
    cust.address = new_address
    cust.phone = new_phone
    cust.google_maps_url = new_maps_url
    cust.location_url = new_maps_url

    if 'deliver_bag' in data:
        cust.deliver_bag = bool(data.get('deliver_bag'))
    if 'customer_status' in data and data.get('customer_status') in ['ACTIVE', 'ARCHIVED']:
        cust.customer_status = data.get('customer_status')

    db.session.commit()
    return jsonify({'success': True, 'customer': cust.to_dict()})


@app.route('/api/master_customers/<int:cust_id>', methods=['DELETE'])
@permission_required('customers.archive')
def delete_master_customer(cust_id):
    cust = db.session.get(MasterCustomer, cust_id)
    if not cust:
        return jsonify({'success': False, 'error': 'Customer not found'}), 404

    cust.customer_status = 'ARCHIVED'
    db.session.commit()
    return jsonify({'success': True, 'message': 'Customer archived successfully.'})


@app.route('/api/templates/<int:template_id>/add_customer', methods=['POST'])
@permission_required('templates.add_customer')
def add_customer_to_template(template_id):
    template = db.session.get(SavedTemplate, template_id)
    if not template or getattr(template, 'is_assigned_instance', False):
        return jsonify({'success': False, 'error': 'Template not found or is an assigned active route'}), 404

    data = request.json or {}
    customer_id = data.get('customer_id')
    customer_ids = data.get('customer_ids')

    if not customer_id and not customer_ids:
        return jsonify({'success': False, 'error': 'customer_id or customer_ids is required'}), 400

    import json
    cust_list = json.loads(template.customers_json or '[]')

    if customer_id:
        master_cust = db.session.get(MasterCustomer, int(customer_id))
        if not master_cust:
            return jsonify({'success': False, 'error': 'Customer not found'}), 404

        for c in cust_list:
            cid = c.get('master_customer_id') or c.get('id')
            if cid == master_cust.id:
                return jsonify({'success': False, 'message': 'Already added to this template.', 'error': 'Already added to this template.'}), 409
            c_name = (c.get('name') or '').strip().lower()
            c_addr = (c.get('address') or '').strip().lower()
            m_name = master_cust.name.strip().lower()
            m_addr = master_cust.address.strip().lower()
            if c_name == m_name and c_addr == m_addr and c_name and c_addr:
                return jsonify({'success': False, 'message': 'Already added to this template.', 'error': 'Already added to this template.'}), 409

        target_truck = 1
        existing_trucks = [int(c.get('truck_id') or 1) for c in cust_list]
        if existing_trucks:
            target_truck = min(existing_trucks)

        stops_on_truck = [c.get('stop_number') or 0 for c in cust_list if int(c.get('truck_id') or 1) == target_truck]
        next_seq = (max(stops_on_truck) + 1) if stops_on_truck else len(cust_list) + 1

        m_url = master_cust.google_maps_url or master_cust.location_url or ''
        new_stop = {
            'id': master_cust.id,
            'master_customer_id': master_cust.id,
            'name': master_cust.name,
            'phone': master_cust.phone or '',
            'address': master_cust.address or '',
            'location_url': m_url,
            'google_maps_url': m_url,
            'lat': master_cust.lat,
            'lng': master_cust.lng,
            'status': 'PENDING',
            'truck_id': target_truck,
            'stop_number': next_seq,
            'confirmation': 'NOT_CONFIRMED',
            'deliver_bag': bool(master_cust.deliver_bag),
            'customer_status': master_cust.customer_status or 'ACTIVE',
            'geocode_quality': master_cust.geocode_quality or 'UNKNOWN',
            'coord_source': master_cust.coord_source or 'UNKNOWN',
            'is_manually_corrected': bool(master_cust.is_manually_corrected)
        }
        cust_list.append(new_stop)
        template.customers_json = json.dumps(cust_list)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f"Customer '{master_cust.name}' added to template '{template.name}'."
        })

    added_count = 0
    skipped_count = 0
    for cid in customer_ids:
        master_cust = db.session.get(MasterCustomer, int(cid))
        if not master_cust:
            continue
        is_dup = False
        for c in cust_list:
            if (c.get('master_customer_id') or c.get('id')) == master_cust.id:
                is_dup = True; break
            c_name = (c.get('name') or '').strip().lower()
            c_addr = (c.get('address') or '').strip().lower()
            if c_name == master_cust.name.strip().lower() and c_addr == master_cust.address.strip().lower() and c_name and c_addr:
                is_dup = True; break
        if is_dup:
            skipped_count += 1
            continue

        target_truck = 1
        stops_on_truck = [c.get('stop_number') or 0 for c in cust_list if int(c.get('truck_id') or 1) == target_truck]
        next_seq = (max(stops_on_truck) + 1) if stops_on_truck else len(cust_list) + 1

        m_url = master_cust.google_maps_url or master_cust.location_url or ''
        cust_list.append({
            'id': master_cust.id,
            'master_customer_id': master_cust.id,
            'name': master_cust.name,
            'phone': master_cust.phone or '',
            'address': master_cust.address or '',
            'location_url': m_url,
            'google_maps_url': m_url,
            'lat': master_cust.lat,
            'lng': master_cust.lng,
            'status': 'PENDING',
            'truck_id': target_truck,
            'stop_number': next_seq,
            'confirmation': 'NOT_CONFIRMED',
            'deliver_bag': bool(master_cust.deliver_bag),
            'customer_status': master_cust.customer_status or 'ACTIVE',
            'geocode_quality': master_cust.geocode_quality or 'UNKNOWN',
            'coord_source': master_cust.coord_source or 'UNKNOWN',
            'is_manually_corrected': bool(master_cust.is_manually_corrected)
        })
        added_count += 1

    template.customers_json = json.dumps(cust_list)
    db.session.commit()
    return jsonify({
        'success': True,
        'added': added_count,
        'skipped': skipped_count,
        'message': f"Added {added_count} customer(s) to '{template.name}'."
    })

# ============================================================================
# TEMPLATE CUSTOMERS TO MASTER CUSTOMER MIGRATION & SYNCHRONIZATION
# ============================================================================

def migrate_saved_template_customers_to_master(db_session=None):
    """
    One-time & idempotent migration that extracts all customer records from every
    SavedTemplate into the MasterCustomer list (master_customers table).

    Deduplication rules:
    - Direct ID / master_customer_id matching against existing MasterCustomer records.
    - Normalized phone number matching (>= 7 digits).
    - Normalized Google Maps URL and/or extracted GPS coordinates matching.
    - Normalized name AND normalized address matching.
    - Exact coordinates matching with matching name.
    - Two different customers are NEVER merged solely because their names match.
    - Safe ID allocation avoiding collisions with existing MasterCustomer and Customer tables.
    - Enriches each template customer entry in customers_json with master_customer_id.
    - Completely idempotent: safe to run multiple times without creating duplicates.
    - Legacy records missing phone/address/URL are handled safely with fallbacks and flagged for review.
    """
    from flask import has_app_context
    if not has_app_context():
        with app.app_context():
            return migrate_saved_template_customers_to_master(db_session=db.session)

    session = db_session or db.session
    import json
    import re

    templates = session.query(SavedTemplate).order_by(SavedTemplate.id.asc()).all()
    existing_mcs = session.query(MasterCustomer).all()
    initial_master_ids = set(mc.id for mc in existing_mcs)

    max_master = session.query(db.func.max(MasterCustomer.id)).scalar() or 0
    max_cust = session.query(db.func.max(Customer.id)).scalar() or 0
    next_available_id = max(max_master, max_cust, 0) + 1

    id_to_mc = {mc.id: mc for mc in existing_mcs}
    phone_to_mc = {}
    for mc in existing_mcs:
        if mc.phone:
            p = normalize_phone_for_dedup(mc.phone)
            if p:
                phone_to_mc[p] = mc

    url_to_mc = {}
    url_coords_to_mc = {}
    for mc in existing_mcs:
        u = (mc.google_maps_url or mc.location_url or '').strip().lower()
        if u:
            url_to_mc[u.rstrip('/')] = mc
            lat_c, lng_c = extract_coords_from_gmaps_url_fast(u)
            if lat_c is not None and lng_c is not None:
                url_coords_to_mc[(round(lat_c, 4), round(lng_c, 4))] = mc
        if mc.lat is not None and mc.lng is not None:
            try:
                url_coords_to_mc[(round(float(mc.lat), 4), round(float(mc.lng), 4))] = mc
            except Exception:
                pass

    name_addr_to_mc = {}
    for mc in existing_mcs:
        n = re.sub(r'\s+', ' ', (mc.name or '').strip().lower())
        a = normalize_address_for_dedup(mc.address)
        if n and a:
            name_addr_to_mc[(n, a)] = mc

    coords_name_to_mc = {}
    for mc in existing_mcs:
        if mc.lat is not None and mc.lng is not None and mc.name:
            try:
                coords_name_to_mc[(round(float(mc.lat), 4), round(float(mc.lng), 4), re.sub(r'\s+', ' ', mc.name.strip().lower()))] = mc
            except Exception:
                pass

    processed_count = 0
    newly_added_ids = set()
    already_existing_count = 0
    duplicates_skipped_count = 0
    manual_review_items = []
    seen_review_keys = set()

    for tmpl in templates:
        raw_json = tmpl.customers_json
        if not raw_json:
            continue
        try:
            cust_list = json.loads(raw_json)
        except Exception:
            continue
        if not isinstance(cust_list, list):
            continue

        tmpl_modified = False

        for c in cust_list:
            if not isinstance(c, dict):
                continue

            raw_id = c.get('id')
            c_name = (c.get('name') or '').strip()

            # Skip depot / facility stops
            is_depot = False
            try:
                if raw_id is not None and int(raw_id) <= -1000:
                    is_depot = True
            except Exception:
                pass
            if c_name in ['End Location / Depot', 'Start Location / Depot', 'Depot'] or c.get('is_depot') is True:
                is_depot = True
            if is_depot:
                continue

            processed_count += 1
            matched_mc = None

            # 1. Direct ID / master_customer_id check
            raw_mid = c.get('master_customer_id')
            if raw_mid:
                try:
                    raw_mid_int = int(raw_mid)
                    if raw_mid_int in id_to_mc:
                        matched_mc = id_to_mc[raw_mid_int]
                except Exception:
                    pass

            # 2. Normalized phone check
            if not matched_mc:
                phone = c.get('phone')
                if phone:
                    p_norm = normalize_phone_for_dedup(phone)
                    if p_norm and p_norm in phone_to_mc:
                        matched_mc = phone_to_mc[p_norm]

            # 3. Google Maps URL / location_url check
            if not matched_mc:
                url = (c.get('google_maps_url') or c.get('location_url') or '').strip()
                if url:
                    u_clean = url.lower().rstrip('/')
                    if u_clean in url_to_mc:
                        matched_mc = url_to_mc[u_clean]
                    else:
                        ulat, ulng = extract_coords_from_gmaps_url_fast(url)
                        if ulat is not None and ulng is not None:
                            ukey = (round(ulat, 4), round(ulng, 4))
                            if ukey in url_coords_to_mc:
                                matched_mc = url_coords_to_mc[ukey]

            # 4. Name + Address check (Requires BOTH name and address to match)
            if not matched_mc:
                n_norm = re.sub(r'\s+', ' ', c_name.lower())
                a_norm = normalize_address_for_dedup(c.get('address') or '')
                if n_norm and a_norm:
                    na_key = (n_norm, a_norm)
                    if na_key in name_addr_to_mc:
                        matched_mc = name_addr_to_mc[na_key]

            # 5. Coordinates + Name check
            if not matched_mc:
                lat = c.get('lat')
                lng = c.get('lng')
                n_norm = re.sub(r'\s+', ' ', c_name.lower())
                if lat is not None and lng is not None and n_norm:
                    try:
                        cn_key = (round(float(lat), 4), round(float(lng), 4), n_norm)
                        if cn_key in coords_name_to_mc:
                            matched_mc = coords_name_to_mc[cn_key]
                    except Exception:
                        pass

            # 6. Legacy stop ID check (only if stop name matches candidate MasterCustomer name)
            if not matched_mc and raw_id is not None:
                try:
                    raw_id_int = int(raw_id)
                    if raw_id_int in id_to_mc:
                        cand_mc = id_to_mc[raw_id_int]
                        cand_n = re.sub(r'\s+', ' ', (cand_mc.name or '').strip().lower())
                        n_norm = re.sub(r'\s+', ' ', c_name.lower())
                        if cand_n and cand_n == n_norm:
                            matched_mc = cand_mc
                except Exception:
                    pass

            if matched_mc:
                if matched_mc.id in initial_master_ids:
                    already_existing_count += 1
                else:
                    duplicates_skipped_count += 1

                if c.get('master_customer_id') != matched_mc.id:
                    c['master_customer_id'] = matched_mc.id
                    tmpl_modified = True
            else:
                # Create NEW MasterCustomer
                review_reasons = []

                name_val = c_name or f"Customer {raw_id or next_available_id}"
                if not c_name:
                    review_reasons.append("Missing customer name; defaulted to generic name")

                raw_addr = (c.get('address') or '').strip()
                lat_val = c.get('lat')
                lng_val = c.get('lng')
                if raw_addr:
                    addr_val = raw_addr
                else:
                    if lat_val is not None and lng_val is not None:
                        try:
                            addr_val = f"Coordinates: {float(lat_val):.6f}, {float(lng_val):.6f}"
                            review_reasons.append("Missing address; auto-generated fallback from GPS coordinates")
                        except Exception:
                            addr_val = "Address Pending Verification"
                            review_reasons.append("Missing address; invalid coordinates")
                    else:
                        addr_val = "Address Pending Verification"
                        review_reasons.append("Missing address; requires manual verification")

                raw_phone = (c.get('phone') or '').strip()
                if raw_phone:
                    is_ph_ok, ph_msg = validate_phone_number(raw_phone)
                    if is_ph_ok:
                        phone_val = ph_msg
                    else:
                        phone_val = raw_phone
                        review_reasons.append(f"Phone number requires review ({raw_phone}): {ph_msg}")
                else:
                    phone_val = None
                    review_reasons.append("Missing phone number")

                raw_url = (c.get('google_maps_url') or c.get('location_url') or '').strip()
                is_coords_ok, lat_f, lng_f, _ = validate_coordinates(lat_val, lng_val)
                if (not is_coords_ok or lat_f is None or lng_f is None) and raw_url:
                    clat, clng = extract_coords_from_gmaps_url_fast(raw_url)
                    if clat is not None and clng is not None:
                        lat_f, lng_f = clat, clng

                if raw_url:
                    is_u_ok, u_msg = validate_google_maps_url(raw_url)
                    if not is_u_ok:
                        review_reasons.append(f"Google Maps URL does not meet standards: {raw_url}")
                    url_val = raw_url
                else:
                    if lat_f is not None and lng_f is not None:
                        url_val = f"https://www.google.com/maps?q={lat_f:.6f},{lng_f:.6f}"
                        review_reasons.append("Missing Google Maps URL; auto-generated from coordinates")
                    else:
                        url_val = ""
                        review_reasons.append("Missing Google Maps URL")

                if lat_f is None or lng_f is None:
                    review_reasons.append("Missing latitude/longitude coordinates")

                # ID allocation
                candidate_id = None
                if c.get('master_customer_id'):
                    try:
                        cand_id_int = int(c.get('master_customer_id'))
                        if cand_id_int > 0 and cand_id_int not in id_to_mc:
                            candidate_id = cand_id_int
                    except Exception:
                        pass
                if not candidate_id:
                    candidate_id = next_available_id
                    next_available_id += 1
                else:
                    next_available_id = max(next_available_id, candidate_id + 1)

                deliver_bag = bool(c.get('deliver_bag', False))
                c_status = c.get('customer_status') or 'ACTIVE'
                geo_qual = c.get('geocode_quality') or ('EXACT' if (lat_f is not None and lng_f is not None) else 'UNKNOWN')
                coord_src = c.get('coord_source') or ('TEMPLATE' if (lat_f is not None and lng_f is not None) else 'UNKNOWN')
                man_corr = bool(c.get('is_manually_corrected', False))

                new_mc = MasterCustomer(
                    id=candidate_id,
                    name=name_val,
                    phone=phone_val,
                    address=addr_val,
                    location_url=url_val,
                    google_maps_url=url_val,
                    lat=lat_f,
                    lng=lng_f,
                    deliver_bag=deliver_bag,
                    customer_status=c_status,
                    geocode_quality=geo_qual,
                    coord_source=coord_src,
                    is_manually_corrected=man_corr
                )
                session.add(new_mc)
                newly_added_ids.add(new_mc.id)
                id_to_mc[new_mc.id] = new_mc

                if phone_val:
                    np = normalize_phone_for_dedup(phone_val)
                    if np:
                        phone_to_mc[np] = new_mc
                if url_val:
                    url_to_mc[url_val.lower().rstrip('/')] = new_mc
                    if lat_f is not None and lng_f is not None:
                        url_coords_to_mc[(round(lat_f, 4), round(lng_f, 4))] = new_mc
                if lat_f is not None and lng_f is not None:
                    url_coords_to_mc[(round(lat_f, 4), round(lng_f, 4))] = new_mc
                    coords_name_to_mc[(round(lat_f, 4), round(lng_f, 4), re.sub(r'\s+', ' ', name_val.lower()))] = new_mc
                n_key = (re.sub(r'\s+', ' ', name_val.lower()), normalize_address_for_dedup(addr_val))
                if n_key[0] and n_key[1]:
                    name_addr_to_mc[n_key] = new_mc

                if review_reasons:
                    review_key = (new_mc.id, tmpl.id)
                    if review_key not in seen_review_keys:
                        seen_review_keys.add(review_key)
                        manual_review_items.append({
                            'template_id': tmpl.id,
                            'template_name': tmpl.name,
                            'customer_id': c.get('id'),
                            'master_customer_id': new_mc.id,
                            'name': name_val,
                            'phone': phone_val,
                            'address': addr_val,
                            'google_maps_url': url_val,
                            'lat': lat_f,
                            'lng': lng_f,
                            'reasons': review_reasons
                        })

                c['master_customer_id'] = new_mc.id
                tmpl_modified = True

        if tmpl_modified:
            tmpl.customers_json = json.dumps(cust_list)

    session.commit()

    return {
        'success': True,
        'templates_scanned': len(templates),
        'processed': processed_count,
        'newly_added': len(newly_added_ids),
        'already_existing': already_existing_count,
        'duplicates_skipped': duplicates_skipped_count,
        'requires_manual_review': len(manual_review_items),
        'manual_review_items': manual_review_items
    }


@app.route('/api/admin/migrate_template_customers', methods=['POST'])
@any_permission_required('customers.create', 'customers.import_excel', 'customers.import_word', 'customers.import_csv')
def api_migrate_template_customers():
    try:
        stats = migrate_saved_template_customers_to_master()
        return jsonify(stats)
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f"Migration failed: {str(e)}"}), 500


@app.route('/api/admin/migrate_template_customers/status', methods=['GET'])
@permission_required('customers.view')
def api_migrate_template_customers_status():
    master_count = MasterCustomer.query.count()
    tmpl_count = SavedTemplate.query.count()
    return jsonify({
        'success': True,
        'master_customers_count': master_count,
        'saved_templates_count': tmpl_count
    })

# ============================================================================
# BULK MASTER CUSTOMER IMPORT (EXCEL, WORD, CSV)
# ============================================================================

import_preview_cache = {}

def normalize_header(header_str):
    if not header_str:
        return ''
    h = str(header_str).strip().lower()
    h = re.sub(r'[\*\(\)]', '', h)
    h = re.sub(r'\b(optional|required|mandatory)\b', '', h)
    return re.sub(r'[\s_\-]+', ' ', h).strip()

def map_column_headers(headers):
    field_synonyms = {
        'name': ['customer name', 'name', 'client name', 'customer', 'client', 'full name', 'party name'],
        'address': ['customer address', 'address', 'location', 'addr', 'street', 'street address', 'site address'],
        'phone': ['phone number', 'phone', 'mobile number', 'mobile', 'contact number', 'contact', 'cell', 'telephone', 'tel', 'phone no', 'mobile no'],
        'location_url': [
            'google maps location url', 'google maps url', 'maps location url', 'location url',
            'google maps link', 'google map link', 'maps link', 'map link', 'google maps',
            'google map', 'maps url', 'map url', 'location link', 'url', 'map'
        ],
        'lat': ['latitude', 'lat'],
        'lng': ['longitude', 'lng', 'long'],
        'deliver_bag': ['deliver bag', 'bag', 'delivery bag', 'deliver bag?', 'bag deliver', 'bag delivery']
    }
    
    mapping = {}
    used_indices = set()
    
    for field, synonyms in field_synonyms.items():
        for idx, h in enumerate(headers):
            if idx in used_indices:
                continue
            norm = normalize_header(h)
            if norm in synonyms:
                mapping[field] = idx
                used_indices.add(idx)
                break

    if 'name' not in mapping:
        for idx, h in enumerate(headers):
            if idx in used_indices:
                continue
            norm = normalize_header(h)
            if 'name' in norm:
                mapping['name'] = idx
                used_indices.add(idx)
                break

    if 'address' not in mapping:
        for idx, h in enumerate(headers):
            if idx in used_indices:
                continue
            norm = normalize_header(h)
            if 'address' in norm or 'street' in norm:
                mapping['address'] = idx
                used_indices.add(idx)
                break

    if 'phone' not in mapping:
        for idx, h in enumerate(headers):
            if idx in used_indices:
                continue
            norm = normalize_header(h)
            if 'phone' in norm or 'mobile' in norm or 'contact' in norm:
                mapping['phone'] = idx
                used_indices.add(idx)
                break

    if 'location_url' not in mapping:
        for idx, h in enumerate(headers):
            if idx in used_indices:
                continue
            norm = normalize_header(h)
            if 'map' in norm or 'url' in norm or 'link' in norm:
                mapping['location_url'] = idx
                used_indices.add(idx)
                break

    return mapping

def _check_mandatory_columns(col_mapping, raw_headers):
    mandatory_fields = ['name', 'address', 'phone', 'location_url']
    missing_cols = [f for f in mandatory_fields if f not in col_mapping]
    if missing_cols:
        col_display = {
            'name': 'Customer Name',
            'address': 'Address',
            'phone': 'Phone Number',
            'location_url': 'Google Maps Location URL'
        }
        missing_names = [col_display[c] for c in missing_cols]
        raise ValueError(f"Uploaded file is missing mandatory column(s): {', '.join(missing_names)}. Detected headers: {raw_headers}. Mandatory columns required: Customer Name, Address, Phone Number, Google Maps Location URL.")

def parse_uploaded_file(file_bytes, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.doc':
        raise ValueError("Legacy .doc format is not supported. Please save or convert your document as modern .docx format and try again.")
    if ext not in ['.xlsx', '.xls', '.docx', '.csv']:
        raise ValueError(f"Unsupported file format '{ext}'. Supported formats: .xlsx, .xls, .docx, .csv")

    raw_headers = []
    data_rows = []

    if ext == '.xlsx':
        import openpyxl, io
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            sheet = wb.worksheets[0]
            rows = list(sheet.iter_rows(values_only=True))
        except Exception as e:
            raise ValueError(f"Failed to read Excel (.xlsx) file: {str(e)}")

        while rows and all(c is None or str(c).strip() == '' for c in rows[0]):
            rows.pop(0)

        if not rows:
            raise ValueError("The uploaded Excel workbook contains no data.")

        raw_headers = [str(c or '').strip() for c in rows[0]]
        col_mapping = map_column_headers(raw_headers)
        _check_mandatory_columns(col_mapping, raw_headers)

        for row_idx, r in enumerate(rows[1:], start=2):
            if all(c is None or str(c).strip() == '' for c in r):
                continue
            row_dict = {'_row_num': row_idx}
            for field, col_idx in col_mapping.items():
                if col_idx < len(r):
                    val = r[col_idx]
                    if isinstance(val, float) and val.is_integer() and field in ['phone']:
                        val = str(int(val))
                    elif val is not None:
                        val = str(val).strip()
                        if val.endswith('.0') and field in ['phone']:
                            val = val[:-2]
                    row_dict[field] = val if val != '' else None
                else:
                    row_dict[field] = None
            data_rows.append(row_dict)

    elif ext == '.xls':
        import xlrd
        try:
            wb = xlrd.open_workbook(file_contents=file_bytes)
            sheet = wb.sheet_by_index(0)
            rows = [sheet.row_values(r) for r in range(sheet.nrows)]
        except Exception as e:
            raise ValueError(f"Failed to read legacy Excel (.xls) file: {str(e)}")

        while rows and all(c is None or str(c).strip() == '' for c in rows[0]):
            rows.pop(0)

        if not rows:
            raise ValueError("The uploaded Excel (.xls) file contains no data.")

        raw_headers = [str(c or '').strip() for c in rows[0]]
        col_mapping = map_column_headers(raw_headers)
        _check_mandatory_columns(col_mapping, raw_headers)

        for row_idx, r in enumerate(rows[1:], start=2):
            if all(c is None or str(c).strip() == '' for c in r):
                continue
            row_dict = {'_row_num': row_idx}
            for field, col_idx in col_mapping.items():
                if col_idx < len(r):
                    val = r[col_idx]
                    if isinstance(val, float) and val.is_integer() and field in ['phone']:
                        val = str(int(val))
                    elif val is not None:
                        val = str(val).strip()
                        if val.endswith('.0') and field in ['phone']:
                            val = val[:-2]
                    row_dict[field] = val if val != '' else None
                else:
                    row_dict[field] = None
            data_rows.append(row_dict)

    elif ext == '.docx':
        import docx, io
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"Failed to read Word (.docx) file: {str(e)}")

        if not doc.tables:
            raise ValueError("No table found in the Word document. Please format customer records in a table with a header row.")

        target_table = None
        col_mapping = None

        for tbl in doc.tables:
            if len(tbl.rows) >= 2:
                headers = [cell.text.strip() for cell in tbl.rows[0].cells]
                mapping = map_column_headers(headers)
                if 'name' in mapping and 'address' in mapping:
                    target_table = tbl
                    col_mapping = mapping
                    raw_headers = headers
                    break

        if not target_table:
            raise ValueError("No valid customer table found in Word document. Please ensure the table has a header row with Customer Name, Address, Phone Number, and Google Maps Location URL.")

        _check_mandatory_columns(col_mapping, raw_headers)

        for row_idx, row in enumerate(target_table.rows[1:], start=2):
            cells = [c.text.strip() for c in row.cells]
            if all(not c for c in cells):
                continue
            row_dict = {'_row_num': row_idx}
            for field, col_idx in col_mapping.items():
                if col_idx < len(cells):
                    val = cells[col_idx].strip()
                    row_dict[field] = val if val else None
                else:
                    row_dict[field] = None
            data_rows.append(row_dict)

    elif ext == '.csv':
        import csv, io
        text_content = None
        for enc in ['utf-8-sig', 'utf-8', 'latin-1']:
            try:
                text_content = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text_content is None:
            raise ValueError("Unable to decode CSV file text encoding.")

        reader = csv.reader(io.StringIO(text_content))
        rows = list(reader)

        while rows and all(c is None or str(c).strip() == '' for c in rows[0]):
            rows.pop(0)

        if not rows:
            raise ValueError("The uploaded CSV contains no data.")

        raw_headers = [str(c or '').strip() for c in rows[0]]
        col_mapping = map_column_headers(raw_headers)
        _check_mandatory_columns(col_mapping, raw_headers)

        for row_idx, r in enumerate(rows[1:], start=2):
            if all(c is None or str(c).strip() == '' for c in r):
                continue
            row_dict = {'_row_num': row_idx}
            for field, col_idx in col_mapping.items():
                if col_idx < len(r):
                    val = r[col_idx].strip()
                    row_dict[field] = val if val != '' else None
                else:
                    row_dict[field] = None
            data_rows.append(row_dict)

    return raw_headers, data_rows


def validate_and_check_duplicates(data_rows):
    existing_customers = MasterCustomer.query.filter(MasterCustomer.customer_status != 'ARCHIVED').all()
    existing_name_addr = {
        (re.sub(r'\s+', ' ', c.name.strip().lower()), normalize_address_for_dedup(c.address)): c.id
        for c in existing_customers
    }
    existing_phones = {}
    for c in existing_customers:
        if c.phone:
            p = normalize_phone_for_dedup(c.phone)
            if p:
                existing_phones[p] = c.id

    seen_in_batch = {}
    seen_phones_in_batch = {}

    processed_rows = []
    valid_count = 0
    duplicate_count = 0
    invalid_count = 0

    for r in data_rows:
        row_num = r.get('_row_num', 0)
        raw_name = (r.get('name') or '').strip()
        raw_address = (r.get('address') or '').strip()
        raw_phone = (r.get('phone') or '').strip()
        location_url = (r.get('location_url') or '').strip()
        raw_bag = r.get('deliver_bag')
        deliver_bag = str(raw_bag).strip().lower() in ['true', '1', 'yes', 'y'] if raw_bag is not None else False

        lat_val = r.get('lat')
        lng_val = r.get('lng')

        errors = []
        is_name_ok, clean_name = validate_customer_name(raw_name)
        if not is_name_ok:
            errors.append("Customer name is required")

        is_addr_ok, clean_addr = validate_customer_address(raw_address)
        if not is_addr_ok:
            errors.append("Customer address is required")

        is_phone_ok, phone_err = validate_phone_number(raw_phone)
        if not is_phone_ok:
            errors.append(phone_err)

        is_url_ok, url_err = validate_google_maps_url(location_url)
        if not is_url_ok:
            errors.append(url_err)

        is_coords_ok, lat_f, lng_f, coord_err = validate_coordinates(lat_val, lng_val)
        if not is_coords_ok:
            errors.append(coord_err)
        elif (lat_f is None or lng_f is None) and is_url_ok:
            c_lat, c_lng = extract_coords_from_gmaps_url_fast(location_url)
            if c_lat is not None and c_lng is not None:
                lat_f = c_lat
                lng_f = c_lng

        status = 'VALID'
        message = 'Ready to import'

        if errors:
            status = 'INVALID'
            message = '; '.join(errors)
        else:
            norm_name = re.sub(r'\s+', ' ', clean_name.lower())
            norm_addr = normalize_address_for_dedup(clean_addr)
            norm_phone = normalize_phone_for_dedup(raw_phone)
            key_name_addr = (norm_name, norm_addr)

            if key_name_addr in seen_in_batch:
                status = 'DUPLICATE'
                message = f"Duplicate name & address in file (matches row {seen_in_batch[key_name_addr]})"
            elif norm_phone and norm_phone in seen_phones_in_batch:
                status = 'DUPLICATE'
                message = f"Duplicate phone in file (matches row {seen_phones_in_batch[norm_phone]})"
            elif key_name_addr in existing_name_addr:
                status = 'DUPLICATE'
                message = f"Already exists in Master List (ID: {existing_name_addr[key_name_addr]})"
            elif norm_phone and norm_phone in existing_phones:
                status = 'DUPLICATE'
                message = f"Phone already registered in Master List (ID: {existing_phones[norm_phone]})"
            else:
                seen_in_batch[key_name_addr] = row_num
                if norm_phone:
                    seen_phones_in_batch[norm_phone] = row_num

        if status == 'VALID':
            valid_count += 1
        elif status == 'DUPLICATE':
            duplicate_count += 1
        else:
            invalid_count += 1

        processed_rows.append({
            'row_num': row_num,
            'name': raw_name,
            'address': raw_address,
            'phone': raw_phone or '',
            'location_url': location_url or '',
            'google_maps_url': location_url or '',
            'lat': lat_f,
            'lng': lng_f,
            'deliver_bag': deliver_bag,
            'status': status,
            'message': message
        })

    return {
        'total_detected': len(processed_rows),
        'valid_count': valid_count,
        'duplicate_count': duplicate_count,
        'invalid_count': invalid_count,
        'ready_to_import_count': valid_count,
        'rows': processed_rows
    }


@app.route('/api/master_customers/import_preview', methods=['POST'])
@admin_required
def master_customers_import_preview():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Empty filename'}), 400

    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized: Login required'}), 401

    ext = os.path.splitext(file.filename)[1].lower()
    if ext in ['.xlsx', '.xls'] and not user_has_permission(user, 'customers.import_excel'):
        return jsonify({'success': False, 'error': "Forbidden: You do not have permission 'customers.import_excel' to import Excel files"}), 403
    elif ext == '.docx' and not user_has_permission(user, 'customers.import_word'):
        return jsonify({'success': False, 'error': "Forbidden: You do not have permission 'customers.import_word' to import Word files"}), 403
    elif ext == '.csv' and not user_has_permission(user, 'customers.import_csv'):
        return jsonify({'success': False, 'error': "Forbidden: You do not have permission 'customers.import_csv' to import CSV files"}), 403

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File size exceeds maximum limit of 10MB.'}), 400

    file_bytes = file.read()
    try:
        raw_headers, data_rows = parse_uploaded_file(file_bytes, file.filename)
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to parse file: {str(e)}'}), 400

    if not data_rows:
        return jsonify({'success': False, 'error': 'No data rows found in the uploaded file.'}), 400

    preview_result = validate_and_check_duplicates(data_rows)
    import uuid
    preview_id = uuid.uuid4().hex
    import_preview_cache[preview_id] = {
        'rows': preview_result['rows'],
        'filename': file.filename,
        'timestamp': time.time()
    }

    now = time.time()
    for k in list(import_preview_cache.keys()):
        if now - import_preview_cache[k]['timestamp'] > 3600:
            import_preview_cache.pop(k, None)

    preview_result['preview_id'] = preview_id
    preview_result['filename'] = file.filename
    preview_result['success'] = True
    return jsonify(preview_result)


@app.route('/api/master_customers/import_confirm', methods=['POST'])
@admin_required
def master_customers_import_confirm():
    data = request.json or {}
    preview_id = data.get('preview_id')
    rows_to_import = data.get('rows')

    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized: Login required'}), 401

    if preview_id and preview_id in import_preview_cache:
        fn = import_preview_cache[preview_id].get('filename', '')
        ext = os.path.splitext(fn)[1].lower()
        if ext in ['.xlsx', '.xls'] and not user_has_permission(user, 'customers.import_excel'):
            return jsonify({'success': False, 'error': "Forbidden: You do not have permission 'customers.import_excel' to import Excel files"}), 403
        elif ext == '.docx' and not user_has_permission(user, 'customers.import_word'):
            return jsonify({'success': False, 'error': "Forbidden: You do not have permission 'customers.import_word' to import Word files"}), 403
        elif ext == '.csv' and not user_has_permission(user, 'customers.import_csv'):
            return jsonify({'success': False, 'error': "Forbidden: You do not have permission 'customers.import_csv' to import CSV files"}), 403

    if not rows_to_import and preview_id:
        cached = import_preview_cache.get(preview_id)
        if cached:
            rows_to_import = cached.get('rows')

    if not rows_to_import:
        return jsonify({'success': False, 'error': 'No customer records provided for import'}), 400

    existing_customers = MasterCustomer.query.filter(MasterCustomer.customer_status != 'ARCHIVED').all()
    existing_name_addr = {
        (re.sub(r'\s+', ' ', c.name.strip().lower()), re.sub(r'\s+', ' ', c.address.strip().lower())): c.id
        for c in existing_customers
    }
    existing_phones = {}
    for c in existing_customers:
        if c.phone:
            p = re.sub(r'[\s\-\(\)\+]', '', c.phone.strip())
            if len(p) >= 7:
                existing_phones[p] = c.id

    max_master_id = db.session.query(db.func.max(MasterCustomer.id)).scalar() or 0
    max_cust_id = db.session.query(db.func.max(Customer.id)).scalar() or 0
    next_id = max(max_master_id, max_cust_id, 0) + 1

    imported_count = 0
    skipped_duplicates = 0
    skipped_invalid = 0

    try:
        with db.session.begin_nested():
            for r in rows_to_import:
                if r.get('status') == 'INVALID':
                    skipped_invalid += 1
                    continue

                name = (r.get('name') or '').strip()
                address = (r.get('address') or '').strip()
                phone = (r.get('phone') or '').strip()
                location_url = (r.get('location_url') or r.get('google_maps_url') or '').strip()
                deliver_bag = bool(r.get('deliver_bag', False))

                is_name_ok, clean_name = validate_customer_name(name)
                is_addr_ok, clean_addr = validate_customer_address(address)
                is_phone_ok, phone_err = validate_phone_number(phone)
                is_url_ok, url_err = validate_google_maps_url(location_url)
                if not (is_name_ok and is_addr_ok and is_phone_ok and is_url_ok):
                    skipped_invalid += 1
                    continue

                lat = r.get('lat')
                lng = r.get('lng')
                is_coords_ok, lat_f, lng_f, _ = validate_coordinates(lat, lng)
                if not is_coords_ok:
                    skipped_invalid += 1
                    continue
                if (lat_f is None or lng_f is None) and is_url_ok:
                    c_lat, c_lng = extract_coords_from_gmaps_url_fast(location_url)
                    if c_lat is not None and c_lng is not None:
                        lat_f, lng_f = c_lat, c_lng

                norm_name = re.sub(r'\s+', ' ', clean_name.lower())
                norm_address = normalize_address_for_dedup(clean_addr)
                norm_phone = normalize_phone_for_dedup(phone)

                if (norm_name, norm_address) in existing_name_addr or (norm_phone and norm_phone in existing_phones):
                    skipped_duplicates += 1
                    continue

                new_cust = MasterCustomer(
                    id=next_id,
                    name=clean_name,
                    address=clean_addr,
                    phone=phone,
                    location_url=location_url,
                    google_maps_url=location_url,
                    lat=lat_f,
                    lng=lng_f,
                    deliver_bag=deliver_bag,
                    customer_status='ACTIVE',
                    geocode_quality='EXACT' if (lat_f is not None and lng_f is not None) else 'UNKNOWN',
                    coord_source='IMPORT' if (lat_f is not None and lng_f is not None) else 'UNKNOWN',
                    is_manually_corrected=(lat_f is not None and lng_f is not None)
                )
                db.session.add(new_cust)
                existing_name_addr[(norm_name, norm_address)] = next_id
                if norm_phone:
                    existing_phones[norm_phone] = next_id
                next_id += 1
                imported_count += 1

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Database error during import: {str(e)}'}), 500

    if preview_id:
        import_preview_cache.pop(preview_id, None)

    return jsonify({
        'success': True,
        'imported': imported_count,
        'skipped_duplicates': skipped_duplicates,
        'skipped_invalid': skipped_invalid,
        'message': f'Successfully imported {imported_count} customer(s).'
    })


@app.route('/api/master_customers/import_error_report/<preview_id>', methods=['GET'])
@admin_required
def master_customers_import_error_report(preview_id):
    cached = import_preview_cache.get(preview_id)
    if not cached:
        return jsonify({'success': False, 'error': 'Preview expired or not found. Please upload the file again.'}), 404

    rows = cached.get('rows', [])
    skipped_rows = [r for r in rows if r.get('status') in ['INVALID', 'DUPLICATE']]

    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Row #', 'Customer Name', 'Address', 'Phone Number', 'Google Maps Location URL', 'Latitude', 'Longitude', 'Status', 'Error / Reason'])

    for r in skipped_rows:
        writer.writerow([
            r.get('row_num', ''),
            r.get('name', ''),
            r.get('address', ''),
            r.get('phone', ''),
            r.get('location_url', ''),
            r.get('lat', '') if r.get('lat') is not None else '',
            r.get('lng', '') if r.get('lng') is not None else '',
            r.get('status', ''),
            r.get('message', '')
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'import_skipped_report_{preview_id[:8]}.csv'
    )


@app.route('/api/master_customers/sample_excel', methods=['GET'])
@any_permission_required('customers.import_excel', 'customers.view')
def master_customers_sample_excel():
    import openpyxl, io
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Customers"

    headers = [
        'Customer Name *',
        'Address *',
        'Phone Number *',
        'Google Maps Location URL *',
        'Latitude (Optional)',
        'Longitude (Optional)'
    ]
    ws.append(headers)

    sample_rows = [
        ['Green Leaf Cafe', '123 Main Street, Ahmedabad', '9876543210', 'https://maps.google.com/?q=23.0225,72.5714', 23.0225, 72.5714]
    ]
    for row in sample_rows:
        ws.append(row)

    header_font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='1D4ED8', end_color='1D4ED8', fill_type='solid')
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 4, 18)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='sample_customers.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/api/master_customers/sample_word', methods=['GET'])
@any_permission_required('customers.import_word', 'customers.view')
def master_customers_sample_word():
    import docx, io

    doc = docx.Document()
    doc.add_heading("TrashTrekyx — Master Customer Import Template", level=1)
    p = doc.add_paragraph(
        "Instructions: Customer Name, Address, Phone Number, and Google Maps Location URL are mandatory. "
        "Latitude and Longitude are optional. Google Maps links must be valid HTTPS URLs (e.g. https://maps.google.com/...). "
        "Rows with missing or invalid mandatory fields will be rejected. Do not alter the header row."
    )
    p.runs[0].font.size = docx.shared.Pt(10)
    p.runs[0].font.italic = True

    headers = [
        'Customer Name *',
        'Address *',
        'Phone Number *',
        'Google Maps Location URL *',
        'Latitude (Optional)',
        'Longitude (Optional)'
    ]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'

    hdr_cells = table.rows[0].cells
    for idx, h in enumerate(headers):
        hdr_cells[idx].text = h
        for p_elem in hdr_cells[idx].paragraphs:
            for run in p_elem.runs:
                run.font.bold = True

    sample_rows = [
        ['Green Leaf Cafe', '123 Main Street, Ahmedabad', '9876543210', 'https://maps.google.com/?q=23.0225,72.5714', '23.0225', '72.5714']
    ]
    for r in sample_rows:
        row_cells = table.add_row().cells
        for idx, val in enumerate(r):
            row_cells[idx].text = str(val)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='sample_customers.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@app.route('/api/master_customers/template/excel', methods=['GET'])
@any_permission_required('customers.import_excel', 'customers.view')
def master_customers_template_excel():
    import openpyxl, io
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.comments import Comment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Customers"

    headers = [
        'Customer Name',
        'Address',
        'Phone Number',
        'Google Maps Location URL',
        'Latitude',
        'Longitude'
    ]
    ws.append(headers)

    font_header = Font(name='Arial', size=11, bold=True, color='FFFFFF')
    fill_mandatory = PatternFill(start_color='1D4ED8', end_color='1D4ED8', fill_type='solid')
    fill_optional = PatternFill(start_color='64748B', end_color='64748B', fill_type='solid')
    align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    ws.row_dimensions[1].height = 28

    comments = [
        "MANDATORY: Customer or business full name.",
        "MANDATORY: Customer street address.",
        "MANDATORY: 10-digit mobile phone number.",
        "MANDATORY: Valid Google Maps link (https://maps.google.com/... or https://goo.gl/maps/...).",
        "OPTIONAL: Latitude in decimal format (e.g. 23.0225).",
        "OPTIONAL: Longitude in decimal format (e.g. 72.5714)."
    ]

    for col_idx, cell in enumerate(ws[1], start=1):
        cell.font = font_header
        cell.alignment = align_center
        cell.border = thin_border
        if col_idx <= 4:
            cell.fill = fill_mandatory
        else:
            cell.fill = fill_optional
        if col_idx <= len(comments):
            cell.comment = Comment(comments[col_idx - 1], 'TrashTrekyx')

    font_data = Font(name='Arial', size=10, color='1E293B')
    align_left = Alignment(horizontal='left', vertical='center')
    align_center_data = Alignment(horizontal='center', vertical='center')

    # Add 10 clean blank entry rows ready for user data entry
    for r_idx in range(2, 12):
        ws.row_dimensions[r_idx].height = 22
        for c_idx in range(1, 7):
            cell = ws.cell(row=r_idx, column=c_idx, value='')
            cell.font = font_data
            cell.border = thin_border
            cell.number_format = '@'
            if c_idx in [3, 5, 6]:
                cell.alignment = align_center_data
            else:
                cell.alignment = align_left

    col_widths = {
        'A': 28,
        'B': 38,
        'C': 22,
        'D': 46,
        'E': 16,
        'F': 16
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    ws.freeze_panes = 'A2'

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='TrashTrekyx_Customer_Template.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/api/master_customers/template/word', methods=['GET'])
@any_permission_required('customers.import_word', 'customers.view')
def master_customers_template_word():
    import docx, io
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    doc = docx.Document()

    heading = doc.add_heading("TrashTrekyx — Blank Customer Import Template", level=1)
    if heading.runs:
        heading.runs[0].font.color.rgb = RGBColor(0x1D, 0x4E, 0xD8)

    p_inst = doc.add_paragraph()
    r1 = p_inst.add_run("Instructions: ")
    r1.bold = True
    r1.font.size = Pt(10)

    r2 = p_inst.add_run(
        "Customer Name, Address, Phone Number, and Google Maps Location URL are mandatory fields. "
        "Latitude and Longitude are optional. Google Maps links must be valid HTTPS URLs "
        "(e.g., https://maps.google.com/... or https://goo.gl/maps/...). "
        "Type or paste your customer records directly into the table rows below. "
        "Do not alter or delete the column header row. Blank rows will be ignored automatically during import."
    )
    r2.font.size = Pt(10)
    r2.font.italic = True
    p_inst.paragraph_format.space_after = Pt(14)

    headers = [
        'Customer Name',
        'Address',
        'Phone Number',
        'Google Maps Location URL',
        'Latitude',
        'Longitude'
    ]

    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'

    hdr_cells = table.rows[0].cells
    for idx, h in enumerate(headers):
        hdr_cells[idx].text = h
        if idx < 4:
            hdr_cells[idx]._tc.get_or_add_tcPr().append(parse_xml('<w:shd ' + nsdecls('w') + ' w:fill="1D4ED8"/>'))
        else:
            hdr_cells[idx]._tc.get_or_add_tcPr().append(parse_xml('<w:shd ' + nsdecls('w') + ' w:fill="64748B"/>'))

        for p_elem in hdr_cells[idx].paragraphs:
            p_elem.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p_elem.runs:
                run.font.bold = True
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for _ in range(10):
        row_cells = table.add_row().cells
        for c in row_cells:
            c.text = ''

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='TrashTrekyx_Customer_Template.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@app.route('/api/master_customers/template/csv', methods=['GET'])
@any_permission_required('customers.import_csv', 'customers.view')
def master_customers_template_csv():
    import csv, io

    headers = [
        'Customer Name',
        'Address',
        'Phone Number',
        'Google Maps Location URL',
        'Latitude',
        'Longitude'
    ]

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\r\n')
    writer.writerow(headers)
    for _ in range(5):
        writer.writerow(['', '', '', '', '', ''])

    csv_bytes = buf.getvalue().encode('utf-8-sig')
    out = io.BytesIO(csv_bytes)
    return send_file(
        out,
        as_attachment=True,
        download_name='TrashTrekyx_Customer_Template.csv',
        mimetype='text/csv'
    )


@app.route('/api/dynamic_recalculate', methods=['POST'])
@permission_required('routes.generate_create')
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
                            s_lat = float(stop_info['lat']) if stop_info.get('lat') is not None else None
                            s_lng = float(stop_info['lng']) if stop_info.get('lng') is not None else None
                            pending_customers.append({
                                'id': str(stop_id),
                                'name': stop_info.get('name', ''),
                                'address': stop_info.get('address', ''),
                                'phone': stop_info.get('phone', ''),
                                'lat': s_lat,
                                'lng': s_lng,
                                'confirmation': stop_info.get('confirmation', 'NOT_CONFIRMED'),
                                'deliver_bag': bool(stop_info.get('deliver_bag', False)),
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
                'deliver_bag': bool(getattr(c, 'deliver_bag', False)),
                'customer_status': getattr(c, 'customer_status', 'ACTIVE') or 'ACTIVE',
                'truck_id': None,
                'status': c.status
            })

        if not truck_starts:
            return jsonify({'error': 'No online trucks found. Open the driver app so it sends GPS data!'}), 400
            
        if not pending_customers:
            return jsonify({'error': 'No pending stops to recalculate.'}), 400
            
        # Filter out end depots from pending_customers and ensure valid coordinates
        real_pending_customers = [c for c in pending_customers if int(c['id']) > -1000 and not (c['confirmation'] == 'CANCELLED' and not c.get('deliver_bag', False)) and c.get('lat') is not None and c.get('lng') is not None]
        
        cancelled_customers = [c for c in pending_customers if c['confirmation'] == 'CANCELLED' and not c.get('deliver_bag', False)]
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
        
        # Safety check: if solver failed or dropped all pending stops, abort to prevent wiping Firebase!
        total_assigned = sum(len(r) for r in new_routes) if new_routes else 0
        if len(real_pending_customers) > 0 and total_assigned == 0:
            return jsonify({'error': 'Optimizer failed to calculate a feasible route. Live routes preserved.'}), 500
        
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
                            "deliver_bag": bool(cust.get("deliver_bag", False)),
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
                            "deliver_bag": bool(c.get("deliver_bag", False)),
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
        try:
            db.session.rollback()
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
