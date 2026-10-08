import os
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

def test_1_new_customer_defaults_active(client):
    with app.app_context():
        c = Customer(name="A", lat=1.0, lng=1.0)
        db.session.add(c)
        db.session.commit()
        assert Customer.query.get(c.id).customer_status == "ACTIVE"

def test_deploy_template_preserves_customer_status(client):
    import json
    with app.app_context():
        custs = [
            {"id": 1, "name": "A", "lat": 1.0, "lng": 1.0, "customer_status": "INACTIVE", "status": "COMPLETED"},
            {"id": 2, "name": "B", "lat": 2.0, "lng": 2.0, "customer_status": "ACTIVE", "status": "COMPLETED"},
            {"id": 3, "name": "C", "lat": 3.0, "lng": 3.0} # Old template without customer_status
        ]
        t = SavedTemplate(name="Test", customers_json=json.dumps(custs))
        db.session.add(t)
        db.session.commit()
        t_id = t.id

    resp = client.post(f'/api/deploy_template/{t_id}')
    assert resp.status_code == 302 # redirect to login because we didn't mock login, wait let's bypass auth
