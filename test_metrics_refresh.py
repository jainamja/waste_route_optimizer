import os
import json
import pytest
import tempfile
from unittest.mock import patch

temp_db_fd, temp_db_path = tempfile.mkstemp(suffix='.db')
sqlite_path = temp_db_path.replace('\\', '/')
os.environ['DATABASE_URL'] = f'sqlite:///{sqlite_path}'

from waste_route_optimizer import app, db, Customer, Metadata, User

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        # Seed Metadata
        start_meta = Metadata(key='start_coords', value=json.dumps(['0.0,0.0', '0.0,0.0']))
        end_meta = Metadata(key='end_coords', value=json.dumps(['10.0,10.0', '10.0,10.0']))
        db.session.add(start_meta)
        db.session.add(end_meta)

        # Seed Trucks and Customers
        # Truck 1
        for i in range(1, 5):
            db.session.add(Customer(id=100+i, name=f'C{i}', lat=float(i), lng=float(i), status='PENDING', truck_id=1, stop_number=i))
        # Depot for Truck 1
        db.session.add(Customer(id=-1001, name='End Location / Depot', lat=10.0, lng=10.0, status='PENDING', truck_id=1, stop_number=5))

        # Truck 2
        for i in range(5, 9):
            db.session.add(Customer(id=100+i, name=f'C{i}', lat=float(i), lng=float(i), status='PENDING', truck_id=2, stop_number=i-4))
        # Depot for Truck 2
        db.session.add(Customer(id=-1002, name='End Location / Depot', lat=10.0, lng=10.0, status='PENDING', truck_id=2, stop_number=5))

        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 1
            yield client

        db.session.remove()
        db.drop_all()
        
    os.close(temp_db_fd)
    os.remove(temp_db_path)

def mock_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data
            
    url = args[0]
    if 'project-osrm.org' in url:
        # Mock OSRM returning fixed 100m distance and 100s duration for each leg
        coords_part = url.split('/')[-1].split('?')[0]
        num_waypoints = len(coords_part.split(';'))
        legs = [{'distance': 100, 'duration': 100} for _ in range(num_waypoints - 1)]
        return MockResponse({'code': 'Ok', 'routes': [{'legs': legs}]})
        
    return MockResponse({}, 404)

def mock_requests_post(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data
    return MockResponse({'idToken': 'fake-token'})
    
def mock_requests_put(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data
    return MockResponse({})
    
def mock_requests_delete(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data
    return MockResponse({})

@patch('requests.get', side_effect=mock_requests_get)
@patch('requests.post', side_effect=mock_requests_post)
@patch('requests.put', side_effect=mock_requests_put)
@patch('requests.delete', side_effect=mock_requests_delete)
def test_metrics_refresh(m_del, m_put, m_post, m_get, client):
    # Call the helper once initially to seed the metrics
    with app.app_context():
        from waste_route_optimizer import recompute_route_metrics
        recompute_route_metrics()
        
    # a. Check initial state via /api/data
    res = client.get('/api/data')
    data = res.get_json()
    assert len(data['route_distances']) == 2
    assert len(data['route_times']) == 2
    
    initial_d1, initial_d2 = data['route_distances'][0], data['route_distances'][1]
    initial_t1, initial_t2 = data['route_times'][0], data['route_times'][1]
    
    # 6 waypoints (start + 4 customers + depot) = 5 legs = 500m
    # 5 legs * 100s + 4 customers * 300s = 1700s
    assert initial_d1 == 500
    assert initial_t1 == 1700
    
    # b. After /api/remove_stop on a middle stop (id=102), truck 1 goes down, truck 2 stays same
    client.post('/api/remove_stop', json={'customer_id': 102, 'truck_id': 1})
    res = client.get('/api/data')
    data = res.get_json()
    assert data['route_distances'][0] < initial_d1
    assert data['route_times'][0] < initial_t1
    assert data['route_distances'][1] == initial_d2
    assert data['route_times'][1] == initial_t2
    
    # c. After /api/add_stop (manual mode), truck 2 goes up
    # We add stop to truck 2
    client.post('/api/add_stop', json={
        'name': 'New Stop', 'phone': '', 'address': '', 'location_url': '',
        'lat': 9.0, 'lng': 9.0, 'target_truck_id': 2, 'target_sequence': 2, 'insert_mode': 'manual'
    })
    res = client.get('/api/data')
    data = res.get_json()
    assert data['route_distances'][1] > initial_d2
    assert data['route_times'][1] > initial_t2

    # d. After /api/update_route_manual moves a stop from truck 1 to truck 2
    # Current truck 1 has ids: 101, 103, 104, -1001
    # Current truck 2 has ids: 105, 106, new, 107, 108, -1002
    client.post('/api/update_route_manual', json={
        'routes': {
            '1': [101, 104, -1001], # Removed 103
            '2': [105, 106, 107, 108, 103, -1002] # Added 103 at end
        }
    })
    res = client.get('/api/data')
    data = res.get_json()
    assert data['route_distances'][0] < initial_d1 - 100 # Should be lower than before
    
    # e. With OSRM mocked to raise, fallback still produces non-zero
    m_get.side_effect = Exception("OSRM Failed")
    client.post('/api/update_route_manual', json={
        'routes': {
            '1': [101, -1001], 
            '2': [105, 106, 107, 108, -1002]
        }
    })
    res = client.get('/api/data')
    data = res.get_json()
    assert data['route_distances'][0] > 0
    assert data['route_times'][0] > 0
    
    # f. Removing a truck's last stop gives 0 and does not crash
    m_get.side_effect = mock_requests_get
    client.post('/api/remove_stop', json={'customer_id': 101, 'truck_id': 1})
    client.post('/api/remove_stop', json={'customer_id': 104, 'truck_id': 1})
        
    res = client.get('/api/data')
    data = res.get_json()
    assert data['route_distances'][0] == 0
    assert data['route_times'][0] == 0
    
    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    pytest.main(['-s', __file__])
