import json
import pytest
from unittest.mock import patch, MagicMock
from waste_route_optimizer import app, db, User, Customer, SavedTemplate, Metadata


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "ADMIN"
            sess["_fresh"] = True
        yield client


def test_open_saved_template_does_not_leak_fake_customers(client):
    """
    Verifies that opening a saved template for viewing/editing does NOT leak:
    1. Residual dummy customers (e.g. 'Customer 17', 'Address 17, Ahmedabad').
    2. Live Firebase stops belonging to other routes (e.g. 'Ritu modi', '9316759794').
    """
    with app.app_context():
        # Setup: Create master template with 2 real customer stops
        real_stops = [
            {"id": 501, "name": "Real Customer A", "lat": 23.01, "lng": 72.51, "truck_id": 1, "stop_number": 1, "address": "Valid Street A", "phone": "1112223334"},
            {"id": 502, "name": "Real Customer B", "lat": 23.02, "lng": 72.52, "truck_id": 1, "stop_number": 2, "address": "Valid Street B", "phone": "1112223335"},
        ]
        template = SavedTemplate(
            name="Clean_Monday_Template",
            metadata_json=json.dumps({"workspace_truck_ids": "[1]"}),
            customers_json=json.dumps(real_stops),
            is_assigned_instance=False
        )
        db.session.add(template)
        db.session.commit()
        tmpl_id = template.id

        # Simulate residual dummy row in Customer table (e.g. leftover from dummy excel)
        dummy_cust = Customer(
            id=17,
            name="Customer 17",
            phone="9876540017",
            address="Address 17, Ahmedabad",
            lat=22.968,
            lng=72.611,
            status="PENDING",
            truck_id=1,
            stop_number=6
        )
        db.session.add(dummy_cust)
        db.session.commit()

        # Simulate Firebase Realtime DB having 'Ritu modi' at stop 19 under route_1
        mock_firebase_routes = {
            "route_1": {
                "stops": {
                    "19": {
                        "name": "Ritu modi",
                        "phone": "9316759794",
                        "address": "K/5 ghanshyam nagar society rto samay subhash bridge ahmedabad",
                        "lat": 23.0648611,
                        "lng": 72.5831111,
                        "status": "PENDING",
                        "sequence": 44
                    }
                }
            }
        }

        try:
            with patch("firebase_client.firebase_client.get_routes", return_value=mock_firebase_routes), \
                 patch("waste_route_optimizer.firebase_client.get_routes", return_value=mock_firebase_routes):

                # 1. Admin opens template to edit (mode=edit)
                res_deploy = client.post(f"/api/deploy_template/{tmpl_id}?mode=edit")
                assert res_deploy.status_code == 200

                # 2. Map frontend requests /api/data to render stops
                res_data = client.get("/api/data")
                assert res_data.status_code == 200
                data = res_data.get_json()

                returned_names = [c["name"] for c in data.get("customers", [])]
                returned_addresses = [str(c.get("address") or "") for c in data.get("customers", [])]
                returned_phones = [str(c.get("phone") or "") for c in data.get("customers", [])]

                # Assert that real template customers ARE present
                assert "Real Customer A" in returned_names
                assert "Real Customer B" in returned_names

                # Assert that fake/residual customers ARE NOT present
                assert "Customer 17" not in returned_names
                assert "Ritu modi" not in returned_names
                assert not any("Address 17" in addr for addr in returned_addresses)
                assert not any("9316759794" in ph for ph in returned_phones)

                # Total customers returned should match exactly the template stops (2)
                assert len(data.get("customers", [])) == 2

        finally:
            # Cleanup
            SavedTemplate.query.filter_by(id=tmpl_id).delete()
            Customer.query.filter_by(id=17).delete()
            Customer.query.filter(Customer.id.in_([501, 502])).delete()
            db.session.commit()
