import pytest
import json
import time
import uuid
from unittest.mock import patch
from waste_route_optimizer import app, db, User, TruckTelemetryHistory, generate_auth_token
from werkzeug.security import generate_password_hash

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        TruckTelemetryHistory.query.delete()

        admin = User.query.filter_by(username='admin_gps_test').first()
        if not admin:
            admin = User(
                username='admin_gps_test',
                password_hash=generate_password_hash('adminpass123'),
                role='ADMIN',
                name='Admin GPS Tester'
            )
            db.session.add(admin)

        driver = User.query.filter_by(username='driver_gps_test').first()
        if not driver:
            driver = User(
                username='driver_gps_test',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Driver GPS Tester',
                truck_id=1
            )
            db.session.add(driver)

        db.session.commit()

    with app.test_client() as c:
        yield c

def get_tokens():
    with app.app_context():
        admin = User.query.filter_by(username='admin_gps_test').first()
        driver = User.query.filter_by(username='driver_gps_test').first()
        return generate_auth_token(admin), generate_auth_token(driver), driver.id

def test_unauthorized_access(client):
    res = client.post('/api/driver/telemetry_sync', json={'records': []})
    assert res.status_code == 401

    res = client.get('/api/truck_telemetry/1')
    assert res.status_code == 401

def test_valid_telemetry_batch_ingestion(client):
    admin_token, driver_token, driver_id = get_tokens()

    now_ms = int(time.time() * 1000)
    batch = [
        {
            "event_id": str(uuid.uuid4()),
            "driver_id": driver_id,
            "truck_id": 1,
            "assignment_id": "gen-1",
            "latitude": 23.0225,
            "longitude": 72.5714,
            "accuracy": 8.5,
            "speed": 6.2,
            "bearing": 180.0,
            "provider": "fused",
            "capture_time": now_ms - 5000,
            "sequence_number": 1
        },
        {
            "event_id": str(uuid.uuid4()),
            "driver_id": driver_id,
            "truck_id": 1,
            "assignment_id": "gen-1",
            "latitude": 23.0230,
            "longitude": 72.5720,
            "accuracy": 12.0,
            "speed": 8.1,
            "bearing": 185.0,
            "provider": "fused",
            "capture_time": now_ms,
            "sequence_number": 2
        }
    ]

    with patch('waste_route_optimizer.requests.patch') as mock_patch, \
         patch('waste_route_optimizer.requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"timestamp": now_ms - 10000}
        
        res = client.post('/api/driver/telemetry_sync', 
                          headers={'Authorization': f'Bearer {driver_token}'},
                          json={'records': batch})
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert data['synced_count'] == 2
        assert data['deduplicated_count'] == 0
        assert data['rejected_count'] == 0

    with app.app_context():
        rows = TruckTelemetryHistory.query.filter_by(truck_id=1).all()
        assert len(rows) == 2

def test_idempotent_deduplication(client):
    admin_token, driver_token, driver_id = get_tokens()

    eid = str(uuid.uuid4())
    record = {
        "event_id": eid,
        "driver_id": driver_id,
        "truck_id": 1,
        "latitude": 23.0225,
        "longitude": 72.5714,
        "accuracy": 10.0,
        "capture_time": int(time.time() * 1000)
    }

    with patch('waste_route_optimizer.requests.patch'), patch('waste_route_optimizer.requests.get'):
        # First upload
        res1 = client.post('/api/driver/telemetry_sync',
                           headers={'Authorization': f'Bearer {driver_token}'},
                           json={'records': [record]})
        assert res1.status_code == 200
        assert res1.get_json()['synced_count'] == 1

        # Second upload with identical event_id
        res2 = client.post('/api/driver/telemetry_sync',
                           headers={'Authorization': f'Bearer {driver_token}'},
                           json={'records': [record]})
        assert res2.status_code == 200
        data2 = res2.get_json()
        assert data2['synced_count'] == 0
        assert data2['deduplicated_count'] == 1

    with app.app_context():
        records_in_db = TruckTelemetryHistory.query.filter_by(event_id=eid).all()
        assert len(records_in_db) == 1

def test_coordinate_validation(client):
    admin_token, driver_token, driver_id = get_tokens()

    bad_records = [
        # Null Island (0, 0)
        {"event_id": str(uuid.uuid4()), "truck_id": 1, "latitude": 0.0, "longitude": 0.0},
        # Latitude out of bounds (> 90)
        {"event_id": str(uuid.uuid4()), "truck_id": 1, "latitude": 95.0, "longitude": 72.5},
        # Longitude out of bounds (<-180)
        {"event_id": str(uuid.uuid4()), "truck_id": 1, "latitude": 23.0, "longitude": -190.0},
        # Invalid non-numeric values
        {"event_id": str(uuid.uuid4()), "truck_id": 1, "latitude": "invalid", "longitude": "coords"}
    ]

    with patch('waste_route_optimizer.requests.patch'), patch('waste_route_optimizer.requests.get'):
        res = client.post('/api/driver/telemetry_sync',
                          headers={'Authorization': f'Bearer {driver_token}'},
                          json={'records': bad_records})
        assert res.status_code == 200
        data = res.get_json()
        assert data['synced_count'] == 0
        assert data['rejected_count'] == 4

def test_driver_truck_assignment_authorization(client):
    admin_token, driver_token, driver_id = get_tokens()

    # Driver is assigned to truck 1, attempting to upload for truck 2
    unassigned_record = {
        "event_id": str(uuid.uuid4()),
        "driver_id": driver_id,
        "truck_id": 2,
        "latitude": 23.0225,
        "longitude": 72.5714,
        "capture_time": int(time.time() * 1000)
    }

    with patch('waste_route_optimizer.requests.patch'), patch('waste_route_optimizer.requests.get'):
        res = client.post('/api/driver/telemetry_sync',
                          headers={'Authorization': f'Bearer {driver_token}'},
                          json={'records': [unassigned_record]})
        assert res.status_code == 200
        data = res.get_json()
        assert data['synced_count'] == 0
        assert data['rejected_count'] == 1

def test_telemetry_history_query(client):
    admin_token, driver_token, driver_id = get_tokens()

    now = int(time.time() * 1000)
    records = [
        TruckTelemetryHistory(
            event_id=f"hist_{i}",
            driver_id=driver_id,
            truck_id=1,
            latitude=23.02 + (i * 0.001),
            longitude=72.57 + (i * 0.001),
            accuracy=10.0,
            speed=5.0,
            bearing=90.0,
            provider="fused",
            capture_time=now + (i * 1000),
            sequence_number=i
        )
        for i in range(5)
    ]
    with app.app_context():
        for r in records:
            db.session.add(r)
        db.session.commit()

    res = client.get('/api/truck_telemetry/1?limit=3', headers={'Authorization': f'Bearer {admin_token}'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['count'] == 3
    assert len(data['telemetry']) == 3

    # Query with since filter
    res_since = client.get(f'/api/truck_telemetry/1?since={now + 3000}', headers={'Authorization': f'Bearer {admin_token}'})
    assert res_since.status_code == 200
    data_since = res_since.get_json()
    assert data_since['count'] == 2

def test_strict_ordering_protection(client):
    admin_token, driver_token, driver_id = get_tokens()

    # Suppose current live position in Firebase is at timestamp 100,000
    current_live_timestamp = 100_000

    # Offline backlog fix captured at timestamp 50,000 (historical backlog)
    stale_record = {
        "event_id": str(uuid.uuid4()),
        "driver_id": driver_id,
        "truck_id": 1,
        "latitude": 23.0100,
        "longitude": 72.5600,
        "accuracy": 15.0,
        "capture_time": 50_000,
        "sequence_number": 1
    }

    with patch('waste_route_optimizer.requests.patch') as mock_patch, \
         patch('waste_route_optimizer.requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "currentLat": 23.0225,
            "currentLng": 72.5714,
            "timestamp": current_live_timestamp
        }

        res = client.post('/api/driver/telemetry_sync',
                          headers={'Authorization': f'Bearer {driver_token}'},
                          json={'records': [stale_record]})
        assert res.status_code == 200
        data = res.get_json()
        assert data['synced_count'] == 1

        # Strict ordering rule: mock_patch must NOT have been called to overwrite truck 1
        # because batch capture_time (50,000) < current live timestamp (100,000)
        truck_patches = [
            call for call in mock_patch.call_args_list
            if '/trucks/1.json' in str(call)
        ]
        assert len(truck_patches) == 0, "Stale historical batch must NOT overwrite newer live position!"
