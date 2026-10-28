import os
import pytest
import pandas as pd
from waste_route_optimizer import (
    app, db, Customer, Metadata,
    clean_address_for_geocoding,
    geocode_address_robust,
    read_data_file
)


def test_clean_address_for_geocoding_strips_noise():
    addr = "1760, Kumud Nagar Society, Akash Parishar Road, B/H Gota UHC, Chanakyapuri"
    cleaned = clean_address_for_geocoding(addr)
    assert "1760" not in cleaned
    assert "B/H" not in cleaned
    assert "Gota UHC" not in cleaned
    assert "Kumud Nagar Society" in cleaned
    assert "Chanakyapuri" in cleaned
    assert "Ahmedabad" in cleaned


def test_clean_address_for_geocoding_handles_pincode_and_typos():
    addr = "1760, KUMUD NAGAR SOCIETY, AKASH PARISHAR ROAD, B/H GOTA UHC, CHANKYAPURI ARE"
    cleaned = clean_address_for_geocoding(addr)
    assert "ARE" not in cleaned
    assert "Area" in cleaned
    assert "Ahmedabad" in cleaned


def test_clean_address_for_geocoding_empty():
    assert clean_address_for_geocoding("") == ""
    assert clean_address_for_geocoding(None) == ""


def test_geocode_address_robust_rejects_city_centroid():
    lat, lng, qual = geocode_address_robust("Ahmedabad, Gujarat")
    assert qual == "FAILED"
    assert lat is None
    assert lng is None


def test_geocode_address_robust_resolves_chanakyapuri():
    addr = "1760, Kumud Nagar Society, Akash Parishar Road, B/H Gota UHC, Chanakyapuri"
    lat, lng, qual = geocode_address_robust(addr)
    assert lat is not None and lng is not None
    assert qual in ["EXACT", "APPROXIMATE"]
    # Verify it is in North-West Ahmedabad (Chanakyapuri / Gota), NOT central Jamalpur (23.0145, 72.5918)
    assert 23.05 <= lat <= 23.12
    assert 72.50 <= lng <= 72.56
    # Centroid distance check
    assert abs(lat - 23.0145) > 0.03


def test_read_data_file_sets_exact_quality_for_coordinates(tmp_path):
    csv_file = tmp_path / "coords.csv"
    df = pd.DataFrame([
        {"Name": "Stop 1", "Coordinates": "23.0500, 72.5500", "Phone": "9876543210"}
    ])
    df.to_csv(csv_file, index=False)
    custs = read_data_file(str(csv_file))
    assert len(custs) == 1
    assert custs[0]["geocode_quality"] == "EXACT"


def test_read_data_file_does_not_drop_unresolvable_stop(tmp_path):
    csv_file = tmp_path / "failed_geocode.csv"
    df = pd.DataFrame([
        {"Name": "Unresolvable Stop", "Address": "xyzzy nowhere 99999", "Phone": "9876543210"}
    ])
    df.to_csv(csv_file, index=False)
    custs = read_data_file(str(csv_file))
    # Must NOT be dropped silently!
    assert len(custs) == 1
    assert custs[0]["geocode_quality"] == "FAILED"
    assert custs[0]["lat"] == pytest.approx(23.0225)
    assert custs[0]["lng"] == pytest.approx(72.5714)


def test_identical_coord_warnings_in_get_data():
    import json
    with app.app_context():
        # Clean up any residual test fixtures
        Customer.query.filter(Customer.id >= 9900).delete()
        # Ensure workspace_truck_ids includes truck 1
        m = Metadata.query.filter_by(key='workspace_truck_ids').first()
        orig_ws = m.value if m else None
        if m:
            m.value = json.dumps([1])
        else:
            db.session.add(Metadata(key='workspace_truck_ids', value=json.dumps([1])))
        db.session.commit()

        # Create 3 customers with identical coordinates
        for i in range(1, 4):
            c = Customer(
                id=9900 + i,
                name=f"Cluster Cust {i}",
                lat=23.02541,
                lng=72.50856,
                truck_id=1,
                stop_number=i,
                status="PENDING",
                geocode_quality="APPROXIMATE"
            )
            db.session.add(c)
        db.session.commit()

        try:
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['user_id'] = 1
                    sess['role'] = 'ADMIN'
                res = client.get('/api/data?truck_id=1')
                assert res.status_code == 200
                data = res.get_json()
                warnings = data.get('identical_coord_warnings', [])
                assert len(warnings) >= 1
                cluster_warn = next((w for w in warnings if round(w['lat'], 4) == round(23.02541, 4)), None)
                assert cluster_warn is not None
                assert cluster_warn['count'] == 3
        finally:
            # Cleanup
            Customer.query.filter(Customer.id >= 9900).delete()
            m = Metadata.query.filter_by(key='workspace_truck_ids').first()
            if m:
                if orig_ws is not None:
                    m.value = orig_ws
                else:
                    db.session.delete(m)
            db.session.commit()


def test_geocode_address_robust_resolves_p3_row49_uppercase():
    addr = "1760, KUMUD NAGAR SOCIETY, AKASH PARISHAR ROAD, B/H GOTA UHC, CHANKYAPURI ARE"
    lat, lng, qual = geocode_address_robust(addr)
    assert lat is not None and lng is not None
    assert qual in ["EXACT", "APPROXIMATE"]
    # Verify it is in North-West Ahmedabad (Chanakyapuri), NOT central Jamalpur (23.0145, 72.5918)
    assert 23.05 <= lat <= 23.12
    assert 72.50 <= lng <= 72.56
    assert abs(lat - 23.0145) > 0.03


def test_read_data_file_shortlink_fallback_chanakyapuri(tmp_path):
    csv_file = tmp_path / "shortlink_fallback.csv"
    df = pd.DataFrame([
        {
            "Name": "PRAJAPATI KIRANKUMAR RAMESHBHAI",
            "Address": "1760, KUMUD NAGAR SOCIETY, AKASH PARISHAR ROAD, B/H GOTA UHC, CHANKYAPURI ARE",
            "Location": "https://maps.app.goo.gl/invalid_timeout_link_fixture_99",
            "Phone": "9876543210"
        }
    ])
    df.to_csv(csv_file, index=False)
    custs = read_data_file(str(csv_file))
    assert len(custs) == 1
    c = custs[0]
    assert c["geocode_quality"] in ["EXACT", "APPROXIMATE"]
    assert 23.05 <= c["lat"] <= 23.12
    assert 72.50 <= c["lng"] <= 72.56
    assert abs(c["lat"] - 23.0145) > 0.03


def test_repair_database_fixes_legacy_centroid():
    with app.app_context():
        # Clean up any leftover fixture
        Customer.query.filter_by(id=9998).delete()
        db.session.commit()

        # Setup: Create a customer stuck at Jamalpur centroid
        test_c = Customer(
            id=9998,
            name="Centroid Repair Test Cust",
            address="1760, KUMUD NAGAR SOCIETY, AKASH PARISHAR ROAD, B/H GOTA UHC, CHANKYAPURI ARE",
            lat=23.0145096,
            lng=72.5917595,
            truck_id=1,
            stop_number=99,
            geocode_quality="APPROXIMATE"
        )
        db.session.add(test_c)
        db.session.commit()

        try:
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['user_id'] = 1
                    sess['role'] = 'ADMIN'

                # Dry run first
                dry_res = client.post('/api/admin/repair_database', json={'dry_run': True})
                assert dry_res.status_code == 200
                dry_data = dry_res.get_json()
                repaired = dry_data.get('details', {}).get('repaired_centroids', [])
                assert any(r['customer_id'] == 9998 for r in repaired)

                # Real execution
                run_res = client.post('/api/admin/repair_database', json={'dry_run': False})
                assert run_res.status_code == 200

                updated = db.session.get(Customer, 9998)
                assert 23.05 <= updated.lat <= 23.12
                assert 72.50 <= updated.lng <= 72.56
                assert abs(updated.lat - 23.0145) > 0.03
                assert updated.geocode_quality in ["EXACT", "APPROXIMATE"]
        finally:
            Customer.query.filter_by(id=9998).delete()
            db.session.commit()


def test_update_customer_details_promotes_quality_to_exact():
    with app.app_context():
        c = Customer(
            id=9995,
            name="Manual Correction Cust",
            lat=23.0225,
            lng=72.5714,
            geocode_quality="FAILED"
        )
        db.session.add(c)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 1
                sess['role'] = 'ADMIN'
            payload = {
                "id": 9995,
                "name": "Manual Correction Cust",
                "lat": 23.0650,
                "lng": 72.5400
            }
            res = client.post('/api/update_customer_details', json=payload)
            assert res.status_code == 200

            updated = db.session.get(Customer, 9995)
            assert updated.lat == pytest.approx(23.0650)
            assert updated.lng == pytest.approx(72.5400)
            assert updated.geocode_quality == "EXACT"

        # Cleanup
        Customer.query.filter_by(id=9995).delete()
        db.session.commit()
