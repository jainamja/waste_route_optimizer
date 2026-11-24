import pytest
import json
import math
from unittest.mock import patch
from waste_route_optimizer import (
    app, db, Customer, Metadata,
    haversine_distance_m,
    get_or_compute_route_geometry
)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        # Clean test state for truck 99
        Customer.query.filter_by(truck_id=99).delete()
        Metadata.query.filter(Metadata.key.like('route_geo_99_%')).delete()
        db.session.commit()

    with app.test_client() as c:
        yield c

    with app.app_context():
        Customer.query.filter_by(truck_id=99).delete()
        Metadata.query.filter(Metadata.key.like('route_geo_99_%')).delete()
        db.session.commit()


def test_haversine_distance():
    # Distance between same coordinates should be 0.0
    d0 = haversine_distance_m(23.06486, 72.58311, 23.06486, 72.58311)
    assert d0 < 0.01

    # Distance across Ahmedabad (~5-15 km)
    d1 = haversine_distance_m(23.0225, 72.5714, 23.0611, 72.4809)
    assert 5000 < d1 < 15000


def test_route_geometry_deduplication_and_caching(client):
    with app.app_context():
        # Create 5 stops: 3 at identical apartment building coordinates, 2 at distant locations
        c1 = Customer(id=9901, name="Customer 1", truck_id=99, stop_number=1, lat=23.06486, lng=72.58311, confirmation="CONFIRMED", status="PENDING")
        c2 = Customer(id=9902, name="Customer 2 (Same Bldg)", truck_id=99, stop_number=2, lat=23.06486, lng=72.58311, confirmation="CONFIRMED", status="PENDING")
        c3 = Customer(id=9903, name="Customer 3 (Same Bldg)", truck_id=99, stop_number=3, lat=23.06487, lng=72.58311, confirmation="CONFIRMED", status="PENDING")
        c4 = Customer(id=9904, name="Customer 4 (Distant)", truck_id=99, stop_number=4, lat=23.07500, lng=72.59000, confirmation="CONFIRMED", status="PENDING")
        c5 = Customer(id=9905, name="Customer 5 (Distant 2)", truck_id=99, stop_number=5, lat=23.08500, lng=72.60000, confirmation="CONFIRMED", status="PENDING")
        db.session.add_all([c1, c2, c3, c4, c5])
        db.session.commit()

        # Mock OSRM call to return synthetic road coordinates
        fake_road_coords = [[72.58311, 23.06486], [72.58500, 23.07000], [72.59000, 23.07500], [72.60000, 23.08500]]
        with patch('requests.get') as mock_get:
            mock_resp = mock_get.return_value
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                'code': 'Ok',
                'routes': [{'geometry': {'coordinates': fake_road_coords}}]
            }

            res = get_or_compute_route_geometry(99, mode='active', force_refresh=True)
            assert res['success'] is True
            assert res['is_road_geometry'] is True
            assert res['total_stops'] == 5
            # Consecutive co-located stops (c1, c2, c3) deduplicated to 1 waypoint -> 3 waypoints total
            assert res['waypoint_count'] == 3
            assert len(res['geometry']['coordinates']) == len(fake_road_coords)

            # Check that it cached in Metadata table
            cached_res = get_or_compute_route_geometry(99, mode='active', force_refresh=False)
            assert cached_res['success'] is True
            assert cached_res.get('cached') is True
            assert cached_res['waypoint_count'] == 3


def test_api_route_geometry_endpoint(client):
    with app.app_context():
        c1 = Customer(id=9910, name="Stop 1", truck_id=99, stop_number=1, lat=23.01, lng=72.51, confirmation="CONFIRMED")
        c2 = Customer(id=9911, name="Stop 2", truck_id=99, stop_number=2, lat=23.02, lng=72.52, confirmation="CONFIRMED")
        db.session.add_all([c1, c2])
        db.session.commit()

    with patch('requests.get') as mock_get:
        mock_resp = mock_get.return_value
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'code': 'Ok',
            'routes': [{'geometry': {'coordinates': [[72.51, 23.01], [72.52, 23.02]]}}]
        }

        resp = client.get('/api/route_geometry/99?mode=active')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['is_road_geometry'] is True
        assert len(data['stops']) == 2
        assert data['stops'][0]['sequence'] == 1
        assert data['stops'][1]['sequence'] == 2


def test_api_live_route_sync_includes_depot_and_metadata(client):
    with app.app_context():
        cust = Customer(id=9920, name="Normal Customer", truck_id=99, stop_number=1, lat=23.05, lng=72.55, address="123 Test St", phone="9988776655")
        depot = Customer(id=-1001, name="End Location / Depot", truck_id=99, stop_number=2, lat=23.02, lng=72.50, address="Depot Central")
        db.session.add_all([cust, depot])
        db.session.commit()

    resp = client.get('/api/live_route_sync')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'route_99' in data['routes']

    stops = data['routes']['route_99']['stops']
    assert '9920' in stops
    assert stops['9920']['name'] == 'Normal Customer'
    assert stops['9920']['address'] == '123 Test St'
    assert stops['9920']['phone'] == '9988776655'

    # Depot stop MUST be included (previously blocked by id > -1000)
    assert '-1001' in stops
    assert stops['-1001']['name'] == 'End Location / Depot'


def test_fallback_when_osrm_unreachable(client):
    with app.app_context():
        c1 = Customer(id=9930, name="Stop A", truck_id=99, stop_number=1, lat=23.10, lng=72.60)
        c2 = Customer(id=9931, name="Stop B", truck_id=99, stop_number=2, lat=23.20, lng=72.70)
        db.session.add_all([c1, c2])
        db.session.commit()

        with patch('requests.get', side_effect=Exception("Connection timed out")):
            res = get_or_compute_route_geometry(99, mode='active', force_refresh=True)
            assert res['success'] is True
            assert res['is_road_geometry'] is False
            assert 'warning' in res
            assert len(res['geometry']['coordinates']) == 2
            assert res['geometry']['coordinates'] == [[72.60, 23.10], [72.70, 23.20]]
