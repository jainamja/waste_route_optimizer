import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
from waste_route_optimizer import app, db, Customer, SavedTemplate

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
        with app.app_context():
            db.drop_all()

@patch('waste_route_optimizer.requests.patch')
def test_assign_driver(mock_patch, client):
    with app.app_context():
        c1 = Customer(name="A", phone="1", address="1", lat=1.0, lng=1.0, truck_id=1, status="PENDING")
        c2 = Customer(name="B", phone="2", address="2", lat=2.0, lng=2.0, truck_id=1, status="COMPLETED")
        c3 = Customer(name="C", phone="3", address="3", lat=3.0, lng=3.0, truck_id=1, status="PENDING")
        db.session.add_all([c1, c2, c3])
        db.session.commit()
        c1_id, c2_id, c3_id = c1.id, c2.id, c3.id

    resp = client.post('/api/assign_driver', json={
        "truck_id": 1,
        "confirmations": {
            str(c1_id): "CANCELLED",
            str(c2_id): "CANCELLED", 
            str(c3_id): "WEIRD_VALUE"
        }
    })
    
    data = resp.get_json()
    assert data["success"] == True
    assert c2_id in data["refused_cancel"]
    
    with app.app_context():
        c1 = Customer.query.get(c1_id)
        c2 = Customer.query.get(c2_id)
        c3 = Customer.query.get(c3_id)
        assert c1.confirmation == "CANCELLED"
        assert c2.confirmation == "NOT_CONFIRMED"
        assert c3.confirmation == "NOT_CONFIRMED"

@patch('waste_route_optimizer.requests.put')
@patch('waste_route_optimizer.requests.patch')
@patch('waste_route_optimizer.ACO_VRP')
def test_dynamic_recalculate(mock_aco, mock_patch, mock_put, client):
    mock_aco.return_value = ([0, 2, 0], 100) 
    with app.app_context():
        c1 = Customer(name="A", phone="1", address="1", lat=1.0, lng=1.0, truck_id=1, status="PENDING", confirmation="CANCELLED", stop_number=1)
        c2 = Customer(name="B", phone="2", address="2", lat=2.0, lng=2.0, truck_id=1, status="PENDING", confirmation="CONFIRMED", stop_number=2)
        c3 = Customer(name="C", phone="3", address="3", lat=3.0, lng=3.0, truck_id=1, status="SKIPPED", confirmation="NOT_CONFIRMED", stop_number=3)
        depot = Customer(name="End Location / Depot", phone="", address="", lat=0.0, lng=0.0, truck_id=1, status="PENDING", confirmation="NOT_CONFIRMED", stop_number=4)
        db.session.add_all([c1, c2, c3, depot])
        db.session.commit()
        c1_id, c2_id = c1.id, c2.id

    resp = client.post('/api/dynamic_recalculate', json={"truck_id": 1})
    if not resp.get_json() or not resp.get_json().get("success"):
        print(resp.get_data(as_text=True))
    assert resp.get_json()["success"] == True
    
    with app.app_context():
        assert Customer.query.get(c1_id).confirmation == "CANCELLED"
        assert Customer.query.get(c2_id).confirmation == "CONFIRMED"

if __name__ == '__main__':
    pytest.main(['-v', 'test_confirmation.py'])
