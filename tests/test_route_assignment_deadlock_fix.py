import os
import sys
import json
import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from waste_route_optimizer import (
    app, db, User, Customer, SavedTemplate
)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(username='admin_assign_tester').first()
        if not admin:
            admin = User(
                username='admin_assign_tester',
                password_hash=generate_password_hash('admintestpass123'),
                role='ADMIN',
                name='Admin Assign Tester',
                is_superadmin=True
            )
            db.session.add(admin)
            db.session.commit()

        driver1 = User.query.filter_by(username='driver_assign_test_1').first()
        if not driver1:
            driver1 = User(
                username='driver_assign_test_1',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Driver Test 1',
                truck_id=1
            )
            db.session.add(driver1)
            db.session.commit()

        driver2 = User.query.filter_by(username='driver_assign_test_2').first()
        if not driver2:
            driver2 = User(
                username='driver_assign_test_2',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Driver Test 2',
                truck_id=2
            )
            db.session.add(driver2)
            db.session.commit()

        admin_id = admin.id
        admin_username = admin.username

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['username'] = admin_username
            sess['role'] = 'ADMIN'
            sess['is_superadmin'] = True
        yield c


def get_test_customer(truck_id=1, status='PENDING', confirmation='NOT_CONFIRMED'):
    cust = Customer.query.filter_by(truck_id=truck_id).first()
    if not cust:
        cust = Customer(
            name='Route Assign Test Customer',
            address='100 Test St, City',
            phone='9998887771',
            lat=23.01,
            lng=72.58,
            truck_id=truck_id,
            stop_number=1,
            status=status,
            confirmation=confirmation,
            deliver_bag=False
        )
        db.session.add(cust)
    else:
        cust.status = status
        cust.confirmation = confirmation
        cust.deliver_bag = False
    db.session.commit()
    return cust.id


def test_route_assignment_with_confirmations_no_deadlock(client):
    """
    Verify that updating customer confirmation to CONFIRMED and deliver_bag=True
    during route assignment persists cleanly without SQLite self-deadlock.
    """
    with app.app_context():
        cid = get_test_customer(truck_id=1, status='PENDING', confirmation='NOT_CONFIRMED')
        driver = User.query.filter_by(username='driver_assign_test_1').first()
        did = driver.id

    payload = {
        'truck_id': 1,
        'driver_id': did,
        'confirmations': {str(cid): 'CONFIRMED'},
        'deliver_bags': {str(cid): True}
    }

    with patch('waste_route_optimizer.set_driver_rtdb_assignment', return_value=(True, 'OK')):
        with patch('waste_route_optimizer.get_firebase_token', return_value='fake_token'):
            with patch('requests.put') as mock_put, patch('requests.patch') as mock_patch:
                mock_put.return_value.status_code = 200
                mock_patch.return_value.status_code = 200

                res = client.post('/api/assign_driver', json=payload)
                assert res.status_code == 200
                data = res.get_json()
                assert data.get('success') is True

    with app.app_context():
        updated_cust = db.session.get(Customer, cid)
        assert updated_cust.confirmation == 'CONFIRMED'
        assert updated_cust.deliver_bag is True


def test_route_assignment_with_cancelled_customer(client):
    """
    Verify that updating a customer confirmation to CANCELLED persists in the database.
    """
    with app.app_context():
        cid = get_test_customer(truck_id=1, status='PENDING', confirmation='NOT_CONFIRMED')
        driver = User.query.filter_by(username='driver_assign_test_1').first()
        did = driver.id

    payload = {
        'truck_id': 1,
        'driver_id': did,
        'confirmations': {str(cid): 'CANCELLED'},
        'deliver_bags': {str(cid): False}
    }

    with patch('waste_route_optimizer.set_driver_rtdb_assignment', return_value=(True, 'OK')):
        with patch('waste_route_optimizer.get_firebase_token', return_value='fake_token'):
            with patch('requests.put') as mock_put, patch('requests.patch') as mock_patch:
                mock_put.return_value.status_code = 200
                mock_patch.return_value.status_code = 200

                res = client.post('/api/assign_driver', json=payload)
                assert res.status_code == 200
                data = res.get_json()
                assert data.get('success') is True

    with app.app_context():
        updated_cust = db.session.get(Customer, cid)
        assert updated_cust.confirmation == 'CANCELLED'


def test_refused_cancel_on_completed_customer(client):
    """
    Verify that an already COMPLETED customer cannot be CANCELLED and is returned in refused_cancel.
    """
    with app.app_context():
        cid = get_test_customer(truck_id=1, status='COMPLETED', confirmation='CONFIRMED')
        driver = User.query.filter_by(username='driver_assign_test_1').first()
        did = driver.id

    payload = {
        'truck_id': 1,
        'driver_id': did,
        'confirmations': {str(cid): 'CANCELLED'},
        'deliver_bags': {str(cid): False}
    }

    with patch('waste_route_optimizer.set_driver_rtdb_assignment', return_value=(True, 'OK')):
        with patch('waste_route_optimizer.get_firebase_token', return_value='fake_token'):
            with patch('requests.put') as mock_put, patch('requests.patch') as mock_patch:
                mock_put.return_value.status_code = 200
                mock_patch.return_value.status_code = 200

                res = client.post('/api/assign_driver', json=payload)
                assert res.status_code == 200
                data = res.get_json()
                assert data.get('success') is True
                assert cid in data.get('refused_cancel', [])

    with app.app_context():
        updated_cust = db.session.get(Customer, cid)
        assert updated_cust.confirmation == 'CONFIRMED'  # Kept original confirmation
        # Reset back to PENDING for clean state
        updated_cust.status = 'PENDING'
        updated_cust.confirmation = 'NOT_CONFIRMED'
        db.session.commit()


def test_driver_eviction_and_transfer_no_deadlock(client):
    """
    Verify that transferring a driver to a truck that evicts another driver succeeds transactionally.
    """
    with app.app_context():
        d1 = User.query.filter_by(username='driver_assign_test_1').first()
        d2 = User.query.filter_by(username='driver_assign_test_2').first()
        d1.truck_id = 1
        d2.truck_id = 2
        db.session.commit()
        d1_id = d1.id
        d2_id = d2.id

    # Assign d1 to truck 2 (evicting d2)
    payload = {
        'truck_id': 2,
        'driver_id': d1_id,
        'confirmations': {},
        'deliver_bags': {}
    }

    with patch('waste_route_optimizer.set_driver_rtdb_assignment', return_value=(True, 'OK')):
        with patch('waste_route_optimizer.get_firebase_token', return_value='fake_token'):
            with patch('requests.put') as mock_put, patch('requests.patch') as mock_patch:
                mock_put.return_value.status_code = 200
                mock_patch.return_value.status_code = 200

                res = client.post('/api/assign_driver', json=payload)
                assert res.status_code == 200
                data = res.get_json()
                assert data.get('success') is True

    with app.app_context():
        d1_after = db.session.get(User, d1_id)
        d2_after = db.session.get(User, d2_id)
        assert d1_after.truck_id == 2
        assert d2_after.truck_id is None  # Evicted


def test_invalid_and_incomplete_route_data(client):
    """
    Verify validation handles missing, empty, or invalid truck/driver data without crashing.
    """
    # Missing truck_id
    res = client.post('/api/assign_driver', json={'driver_id': 1})
    assert res.status_code == 400
    assert 'Missing truck_id' in res.get_json().get('error', '')

    # Invalid truck_id
    res = client.post('/api/assign_driver', json={'truck_id': 'invalid_truck'})
    assert res.status_code == 400
    assert 'Invalid truck_id' in res.get_json().get('error', '')

    # Non-existent driver_id
    res = client.post('/api/assign_driver', json={'truck_id': 1, 'driver_id': 999999})
    assert res.status_code == 404
    assert 'Driver not found' in res.get_json().get('error', '')


def test_unauthenticated_access_blocked():
    """
    Verify unauthenticated users cannot access /api/assign_driver.
    """
    with app.test_client() as anon_client:
        res = anon_client.post('/api/assign_driver', json={'truck_id': 1})
        assert res.status_code in [302, 401, 403]
