import os
import json
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from waste_route_optimizer import (
    app, db, Customer, Metadata, SavedTemplate, UrlCoordinateCache,
    clean_address_for_geocoding,
    geocode_address_robust,
    resolve_gmaps_url,
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


def test_city_level_geocoder_result_becomes_failed():
    # City-level / locality results must become FAILED with lat/lng None
    lat, lng, qual = geocode_address_robust("Ahmedabad, Gujarat")
    assert qual == "FAILED"
    assert lat is None
    assert lng is None

    lat2, lng2, qual2 = geocode_address_robust("Ahmedabad")
    assert qual2 == "FAILED"
    assert lat2 is None
    assert lng2 is None


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
    assert custs[0]["coord_source"] == "FILE"


def test_read_data_file_does_not_drop_unresolvable_stop(tmp_path):
    csv_file = tmp_path / "failed_geocode.csv"
    df = pd.DataFrame([
        {"Name": "Unresolvable Stop", "Address": "xyzzy nowhere 99999", "Phone": "9876543210"}
    ])
    df.to_csv(csv_file, index=False)
    custs = read_data_file(str(csv_file))
    # Must NOT be dropped silently, and must NOT use hardcoded 23.0225 as real coordinates
    assert len(custs) == 1
    assert custs[0]["geocode_quality"] == "FAILED"
    assert custs[0]["coord_source"] == "FAILED"
    assert custs[0]["lat"] is None
    assert custs[0]["lng"] is None


def test_shared_building_cluster_stays_exact(tmp_path):
    # Requirement 2: Do NOT demote clusters whose coordinates came from file or resolved Maps link
    csv_file = tmp_path / "amaltas_cluster.csv"
    shared_url = "https://maps.app.goo.gl/3FTMrJuyKGXdFENg7"
    # Pre-cache the building entry coordinates in UrlCoordinateCache
    with app.app_context():
        entry = UrlCoordinateCache(url=shared_url, lat=23.02541, lng=72.50856)
        db.session.merge(entry)
        db.session.commit()

    df = pd.DataFrame([
        {"Name": "Sangita Jain", "Location": shared_url, "Address": "A-54, Amaltas Apartment"},
        {"Name": "Savita Bansal", "Location": shared_url, "Address": "C-23, Amaltas Apartment"},
        {"Name": "Sweetu Patel", "Location": shared_url, "Address": "A-11, Amaltas Apartment"},
    ])
    df.to_csv(csv_file, index=False)
    custs = read_data_file(str(csv_file))
    assert len(custs) == 3
    # Shared building clusters with Maps link MUST remain EXACT, not demoted to APPROXIMATE
    for c in custs:
        assert c["geocode_quality"] == "EXACT"
        assert c["coord_source"] == "MAPS_LINK"
        assert c["lat"] == pytest.approx(23.02541)
        assert c["lng"] == pytest.approx(72.50856)


def test_row49_shortlink_timeout_retry_and_fallback(tmp_path):
    # Requirement 1 & Row 49: Shortlink timeout with retries, then fallback to address geocoding
    csv_file = tmp_path / "row49_test.csv"
    df = pd.DataFrame([
        {
            "Name": "PRAJAPATI KIRANKUMAR RAMESHBHAI",
            "Address": "1760, KUMUD NAGAR SOCIETY, AKASH PARISHAR ROAD, B/H GOTA UHC, CHANKYAPURI ARE",
            "Location": "https://maps.app.goo.gl/unresolvable_simulated_timeout_link_99",
            "Phone": "9687430655"
        }
    ])
    df.to_csv(csv_file, index=False)

    call_count = [0]
    import requests
    orig_get = requests.get

    def mock_get(url, *args, **kwargs):
        if "unresolvable_simulated_timeout_link_99" in url:
            call_count[0] += 1
            raise requests.exceptions.ConnectTimeout("Simulated timeout for retry test")
        return orig_get(url, *args, **kwargs)

    with patch("requests.get", side_effect=mock_get):
        custs = read_data_file(str(csv_file))

    # Must have retried at least twice before giving up on the link
    assert call_count[0] >= 2
    assert len(custs) == 1
    c = custs[0]
    # Address fallback must place customer in NW Ahmedabad (Chanakyapuri)
    assert c["coord_source"] == "GEOCODE"
    assert c["geocode_quality"] in ["EXACT", "APPROXIMATE"]
    assert 23.05 <= c["lat"] <= 23.12
    assert 72.50 <= c["lng"] <= 72.56
    assert abs(c["lat"] - 23.0145) > 0.03

    # Failed resolution must NEVER be saved in UrlCoordinateCache as (None, None)
    with app.app_context():
        entry = db.session.get(UrlCoordinateCache, "https://maps.app.goo.gl/unresolvable_simulated_timeout_link_99")
        assert entry is None


def test_manual_correction_survives_reoptimize_and_template_redeploy():
    # Requirement 5: Manual correction must be permanent and survive save/redeploy
    with app.app_context():
        Customer.query.filter_by(id=9991).delete()
        SavedTemplate.query.filter_by(name="Manual_Correction_Test_Template").delete()
        db.session.commit()

        m = Metadata.query.filter_by(key='workspace_truck_ids').first()
        if m:
            m.value = json.dumps([1])
        else:
            db.session.add(Metadata(key='workspace_truck_ids', value=json.dumps([1])))

        c = Customer(
            id=9991,
            name="Manual Move Cust",
            address="Original Stored Address",
            lat=23.0100,
            lng=72.5100,
            truck_id=1,
            stop_number=1,
            geocode_quality="APPROXIMATE",
            coord_source="GEOCODE",
            is_manually_corrected=False
        )
        db.session.add(c)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 1
                sess['role'] = 'ADMIN'

            # 1. Admin manually adjusts pin
            payload = {
                "id": 9991,
                "name": "Manual Move Cust",
                "lat": 23.0850,
                "lng": 72.5350
            }
            res_upd = client.post('/api/update_customer_details', json=payload)
            assert res_upd.status_code == 200

            updated = db.session.get(Customer, 9991)
            assert updated.lat == pytest.approx(23.0850)
            assert updated.lng == pytest.approx(72.5350)
            assert updated.is_manually_corrected is True
            assert updated.coord_source == "MANUAL"
            assert updated.geocode_quality == "EXACT"

            # 2. Admin saves template
            save_res = client.post('/api/save_template', json={
                "name": "Manual_Correction_Test_Template",
                "metadata": {"workspace_truck_ids": "[1]"}
            })
            assert save_res.status_code == 200

            tmpl = SavedTemplate.query.filter_by(name="Manual_Correction_Test_Template").first()
            assert tmpl is not None
            tmpl_custs = json.loads(tmpl.customers_json)
            tc = next(x for x in tmpl_custs if x['id'] == 9991)
            assert tc['lat'] == pytest.approx(23.0850)
            assert tc['lng'] == pytest.approx(72.5350)
            assert tc['is_manually_corrected'] is True
            assert tc['coord_source'] == "MANUAL"

            # 3. Simulate deploying template to another truck
            dep_res = client.post(f'/api/deploy_template/{tmpl.id}?mode=edit')
            assert dep_res.status_code == 200

            dep_cust = db.session.get(Customer, 9991)
            assert dep_cust.lat == pytest.approx(23.0850)
            assert dep_cust.lng == pytest.approx(72.5350)
            assert dep_cust.is_manually_corrected is True
            assert dep_cust.coord_source == "MANUAL"
            assert dep_cust.geocode_quality == "EXACT"

        # Cleanup
        Customer.query.filter_by(id=9991).delete()
        SavedTemplate.query.filter_by(name="Manual_Correction_Test_Template").delete()
        db.session.commit()


def test_identical_coord_warnings_in_get_data():
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

        # Create 3 customers with identical geocoded coordinates
        for i in range(1, 4):
            c = Customer(
                id=9900 + i,
                name=f"Cluster Cust {i}",
                lat=23.02541,
                lng=72.50856,
                truck_id=1,
                stop_number=i,
                status="PENDING",
                coord_source="GEOCODE",
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
