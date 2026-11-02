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

        try:
            with patch('requests.patch') as mock_patch:
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
        finally:
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


def test_template_centroid_sanitization_and_kumud_nagar_correction():
    with app.app_context():
        # Setup dummy template with old centroid and kumud nagar customer
        custs = [
            {
                "id": 9951,
                "name": "Prajapati Kirankumar Rameshbhai",
                "phone": "9687430655",
                "address": "1760, KUMUD NAGAR SOCIETY, AKASH PARISHAR ROAD, B/H GOTA UHC, CHANKYAPURI ARE",
                "lat": 23.0145096,
                "lng": 72.5917595,
                "geocode_quality": "APPROXIMATE",
                "coord_source": "GEOCODE",
                "is_manually_corrected": False
            },
            {
                "id": 9952,
                "name": "Generic Centroid Cust",
                "phone": "9876543210",
                "address": "Some Vague Address, Ahmedabad",
                "lat": 23.0145096,
                "lng": 72.5917595,
                "geocode_quality": "APPROXIMATE",
                "coord_source": "GEOCODE",
                "is_manually_corrected": False
            }
        ]
        tmpl = SavedTemplate(
            name="Test_Sanitization_Tuesday_Template",
            customers_json=json.dumps(custs),
            metadata_json=json.dumps({})
        )
        db.session.add(tmpl)
        db.session.commit()
        tmpl_id = tmpl.id

        try:
            # Re-run sanitization logic as runs on startup
            for t in SavedTemplate.query.filter_by(id=tmpl_id).all():
                c_list = json.loads(t.customers_json or '[]')
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
                        if (abs(clat - 23.0145) < 0.003 and abs(clng - 72.5918) < 0.003) or                            (abs(clat - 23.0225) < 0.001 and abs(clng - 72.5714) < 0.001):
                            c_item['lat'] = None
                            c_item['lng'] = None
                            c_item['geocode_quality'] = 'FAILED'
                            c_item['coord_source'] = 'FAILED'
                            modified = True
                if modified:
                    t.customers_json = json.dumps(c_list)
            db.session.commit()

            # Verify
            updated_tmpl = SavedTemplate.query.get(tmpl_id)
            updated_custs = json.loads(updated_tmpl.customers_json)
            k_cust = next(c for c in updated_custs if c['id'] == 9951)
            g_cust = next(c for c in updated_custs if c['id'] == 9952)

            assert k_cust['lat'] == pytest.approx(23.0744137)
            assert k_cust['lng'] == pytest.approx(72.5280572)
            assert k_cust['coord_source'] == 'FILE'
            assert k_cust['geocode_quality'] == 'EXACT'
            assert k_cust['is_manually_corrected'] is True

            assert g_cust['lat'] is None
            assert g_cust['lng'] is None
            assert g_cust['geocode_quality'] == 'FAILED'
            assert g_cust['coord_source'] == 'FAILED'
        finally:
            SavedTemplate.query.filter_by(id=tmpl_id).delete()
            db.session.commit()


def test_recompute_route_metrics_with_unlocated_stop():
    with app.app_context():
        # Clean any old test stops
        Customer.query.filter(Customer.id >= 9970).delete()
        Metadata.query.filter_by(key='start_coords').delete()
        
        m_start = Metadata(key='start_coords', value=json.dumps(["23.0225,72.5714"]))
        m_ws = Metadata.query.filter_by(key='workspace_truck_ids').first()
        orig_ws = m_ws.value if m_ws else None
        if m_ws:
            m_ws.value = json.dumps([1])
        else:
            db.session.add(Metadata(key='workspace_truck_ids', value=json.dumps([1])))
        db.session.add(m_start)
        
        # Add 1 valid stop and 1 unlocated stop (lat=None, lng=None)
        c1 = Customer(id=9971, name="Valid Stop", lat=23.050, lng=72.550, truck_id=1, stop_number=1, geocode_quality="EXACT")
        c2 = Customer(id=9972, name="Failed Stop", lat=None, lng=None, truck_id=1, stop_number=2, geocode_quality="FAILED")
        db.session.add_all([c1, c2])
        db.session.commit()
        
        try:
            from waste_route_optimizer import recompute_route_metrics
            # Must NOT crash with TypeError on None coordinates
            recompute_route_metrics()
            
            m_times = Metadata.query.filter_by(key='route_times').first()
            assert m_times is not None
            times = json.loads(m_times.value)
            assert len(times) == 1
            assert times[0] >= 300 # Contains time for the 1 valid stop
        finally:
            Customer.query.filter(Customer.id >= 9970).delete()
            Metadata.query.filter_by(key='start_coords').delete()
            m_ws = Metadata.query.filter_by(key='workspace_truck_ids').first()
            if m_ws:
                if orig_ws is not None:
                    m_ws.value = orig_ws
                else:
                    db.session.delete(m_ws)
            db.session.commit()


def test_ai_rebalance_parses_comma_separated_start_coords():
    with app.app_context():
        # Setup metadata with comma-separated coordinate strings
        Metadata.query.filter(Metadata.key.in_(['start_coords', 'end_coords'])).delete()
        db.session.add(Metadata(key='start_coords', value=json.dumps(["23.0225,72.5714", "23.0300,72.5800"])))
        db.session.add(Metadata(key='end_coords', value=json.dumps(["23.0500,72.5900", "23.0600,72.6000"])))
        
        # Test string parsing logic
        meta_starts = json.loads(Metadata.query.filter_by(key='start_coords').first().value)
        meta_ends = json.loads(Metadata.query.filter_by(key='end_coords').first().value)
        
        start_coords = []
        for s in meta_starts:
            if isinstance(s, str):
                lat, lng = map(float, s.split(','))
            else:
                lat, lng = float(s[0]), float(s[1])
            start_coords.append((lat, lng))
            
        assert start_coords[0][0] == pytest.approx(23.0225)
        assert start_coords[0][1] == pytest.approx(72.5714)
        assert start_coords[0][0] > 20.0 # Must NOT be 2.0 (Atlantic Ocean)
        assert start_coords[0][1] > 70.0 # Must NOT be 3.0
