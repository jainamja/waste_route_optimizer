import os
import io
import json
import csv
import tempfile
import pytest
import openpyxl
from docx import Document
from werkzeug.security import generate_password_hash

from waste_route_optimizer import (
    app, db, User, Customer, SavedTemplate, MasterCustomer,
    validate_customer_name, validate_customer_address, validate_phone_number,
    validate_google_maps_url, validate_coordinates, extract_coords_from_gmaps_url_fast,
    parse_uploaded_file, map_column_headers, normalize_header,
    _check_mandatory_columns, read_data_file
)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        # Clean master customers for clean test run
        MasterCustomer.query.delete()

        admin = User.query.filter_by(username='admin_validator').first()
        if not admin:
            admin = User(
                username='admin_validator',
                password_hash=generate_password_hash('adminpass123'),
                role='ADMIN',
                name='Admin Validator',
                is_superadmin=True
            )
            db.session.add(admin)
            db.session.commit()

        # Ensure a test template exists
        t = db.session.get(SavedTemplate, 101)
        if not t:
            t = SavedTemplate(id=101, name='Test Route 101', customers_json='[]', is_assigned_instance=False)
            db.session.add(t)
        else:
            t.customers_json = '[]'
        db.session.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            with app.app_context():
                a = User.query.filter_by(username='admin_validator').first()
                sess['user_id'] = a.id
        yield client

# ============================================================================
# 1. UNIT VALIDATION TESTS FOR MANDATORY / OPTIONAL FIELDS
# ============================================================================

def test_unit_validate_customer_name():
    # Valid
    ok, val = validate_customer_name("  Green Leaf Cafe  ")
    assert ok is True
    assert val == "Green Leaf Cafe"

    # Missing / whitespace
    ok, err = validate_customer_name("")
    assert ok is False
    assert "Customer Name" in err

    ok, err = validate_customer_name("    ")
    assert ok is False

    ok, err = validate_customer_name(None)
    assert ok is False

def test_unit_validate_customer_address():
    # Valid
    ok, val = validate_customer_address("  123 Main Street, Sector 5, Ahmedabad  ")
    assert ok is True
    assert val == "123 Main Street, Sector 5, Ahmedabad"

    # Missing / whitespace
    ok, err = validate_customer_address("")
    assert ok is False
    assert "Address" in err

    ok, err = validate_customer_address("   ")
    assert ok is False

    ok, err = validate_customer_address(None)
    assert ok is False

def test_unit_validate_phone_number():
    # Valid 10-digit Indian
    ok, val = validate_phone_number("9876543210")
    assert ok is True
    assert val == "9876543210"

    # Valid with +91
    ok, val = validate_phone_number("+91 98765 43210")
    assert ok is True
    assert "98765" in val

    # Valid with 0 prefix
    ok, val = validate_phone_number("09876543210")
    assert ok is True

    # Valid international (12 digits)
    ok, val = validate_phone_number("+1 (555) 234-5678")
    assert ok is True

    # Invalid: missing
    ok, err = validate_phone_number("")
    assert ok is False
    assert "Phone" in err

    ok, err = validate_phone_number(None)
    assert ok is False

    # Invalid: too short (< 7 digits)
    ok, err = validate_phone_number("12345")
    assert ok is False
    assert ("short" in err.lower() or "invalid" in err.lower())

    # Invalid: too long (> 15 digits)
    ok, err = validate_phone_number("12345678901234567")
    assert ok is False
    assert "long" in err.lower()

    # Invalid: non-numeric garbage
    ok, err = validate_phone_number("call-me-now")
    assert ok is False

def test_unit_validate_google_maps_url():
    # Valid HTTPS Google Maps variations
    valid_urls = [
        "https://maps.google.com/?q=23.0225,72.5714",
        "https://www.google.com/maps/place/Ahmedabad,+Gujarat/@23.0225,72.5714,14z",
        "https://maps.app.goo.gl/wE9AbCd123",
        "https://goo.gl/maps/kP456XyZ",
        "https://google.com/maps?cid=1234567890",
        "https://www.google.co.in/maps/@23.0225,72.5714,15z"
    ]
    for u in valid_urls:
        ok, val = validate_google_maps_url(u)
        assert ok is True, f"Expected {u} to be valid, got {val}"
        assert val.startswith("https://")

    # Invalid: missing / whitespace
    ok, err = validate_google_maps_url("")
    assert ok is False
    assert "Google Maps" in err

    ok, err = validate_google_maps_url(None)
    assert ok is False

    # Invalid: HTTP (not HTTPS)
    ok, err = validate_google_maps_url("http://maps.google.com/?q=23.0225,72.5714")
    assert ok is False
    assert "HTTPS" in err

    # Invalid: Non-Google domain
    ok, err = validate_google_maps_url("https://facebook.com/maps")
    assert ok is False
    assert "Google Maps" in err

    ok, err = validate_google_maps_url("https://example.com/location")
    assert ok is False

    ok, err = validate_google_maps_url("https://bing.com/maps")
    assert ok is False

    # Invalid: Plain text description
    ok, err = validate_google_maps_url("Near City Center Mall, Opposite Bus Stand")
    assert ok is False

def test_unit_validate_coordinates():
    # Valid
    ok, lat, lng, err = validate_coordinates(23.0225, 72.5714)
    assert ok is True
    assert lat == 23.0225 and lng == 72.5714
    assert err is None

    # Optional / empty coordinates allowed
    ok, lat, lng, err = validate_coordinates(None, None)
    assert ok is True
    assert lat is None and lng is None

    ok, lat, lng, err = validate_coordinates("", "")
    assert ok is True
    assert lat is None and lng is None

    # Out of range Latitude (> 90 or < -90)
    ok, lat, lng, err = validate_coordinates(95.0, 72.5714)
    assert ok is False
    assert "Latitude" in err

    ok, lat, lng, err = validate_coordinates(-91.0, 72.5714)
    assert ok is False

    # Out of range Longitude (> 180 or < -180)
    ok, lat, lng, err = validate_coordinates(23.0225, 185.0)
    assert ok is False
    assert "Longitude" in err

    ok, lat, lng, err = validate_coordinates(23.0225, -181.0)
    assert ok is False

def test_unit_extract_coords_from_gmaps_url_fast():
    # @lat,lng pattern
    url1 = "https://www.google.com/maps/place/Ahmedabad/@23.022500,72.571400,14z"
    c1 = extract_coords_from_gmaps_url_fast(url1)
    assert c1 != (None, None)
    assert abs(c1[0] - 23.0225) < 1e-4 and abs(c1[1] - 72.5714) < 1e-4

    # ?q=lat,lng pattern
    url2 = "https://maps.google.com/?q=23.0300,72.5800"
    c2 = extract_coords_from_gmaps_url_fast(url2)
    assert c2 != (None, None)
    assert abs(c2[0] - 23.0300) < 1e-4 and abs(c2[1] - 72.5800) < 1e-4

    # Short URL without inline coordinates
    url3 = "https://maps.app.goo.gl/AbCdEf123"
    c3 = extract_coords_from_gmaps_url_fast(url3)
    assert c3 == (None, None)

# ============================================================================
# 2. MANUAL ADD CUSTOMER FORM API TESTS (POST /api/master_customers)
# ============================================================================

def test_api_create_customer_success_all_fields(client):
    payload = {
        "name": "Sunrise Cafe",
        "address": "45 Riverfront Road, Ahmedabad",
        "phone": "9825012345",
        "google_maps_url": "https://maps.google.com/?q=23.0225,72.5714",
        "lat": 23.0225,
        "lng": 72.5714
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    cust = data["customer"]
    assert cust["name"] == "Sunrise Cafe"
    assert cust["address"] == "45 Riverfront Road, Ahmedabad"
    assert cust["phone"] == "9825012345"
    assert cust["google_maps_url"] == "https://maps.google.com/?q=23.0225,72.5714"
    assert cust["location_url"] == "https://maps.google.com/?q=23.0225,72.5714"
    assert cust["lat"] == 23.0225
    assert cust["lng"] == 72.5714

def test_api_create_customer_success_without_coords(client):
    # Latitude and Longitude are strictly optional
    payload = {
        "name": "Moonlight Bakery",
        "address": "12 Baker Street, Ahmedabad",
        "phone": "9825098765",
        "google_maps_url": "https://maps.app.goo.gl/k98AbCdEf"
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    cust = data["customer"]
    assert cust["name"] == "Moonlight Bakery"
    assert cust["lat"] is None
    assert cust["lng"] is None

def test_api_create_customer_fast_coord_extraction(client):
    # Coords omitted, but extractable from URL
    payload = {
        "name": "Riverview Bistro",
        "address": "88 Promenade, Ahmedabad",
        "phone": "9825055555",
        "google_maps_url": "https://www.google.com/maps/@23.0400,72.5900,15z"
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    cust = data["customer"]
    assert cust["lat"] == 23.04
    assert cust["lng"] == 72.59

def test_api_create_customer_rejection_missing_name(client):
    payload = {
        "name": "   ",
        "address": "Valid Address",
        "phone": "9825012345",
        "google_maps_url": "https://maps.google.com/?q=23.02,72.57"
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 400
    assert "Customer Name" in res.get_json()["error"]

def test_api_create_customer_rejection_missing_address(client):
    payload = {
        "name": "Valid Name",
        "address": "",
        "phone": "9825012345",
        "google_maps_url": "https://maps.google.com/?q=23.02,72.57"
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 400
    assert "Address" in res.get_json()["error"]

def test_api_create_customer_rejection_missing_phone(client):
    payload = {
        "name": "Valid Name",
        "address": "Valid Address",
        "phone": "",
        "google_maps_url": "https://maps.google.com/?q=23.02,72.57"
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 400
    assert "Phone" in res.get_json()["error"]

def test_api_create_customer_rejection_invalid_phone(client):
    payload = {
        "name": "Valid Name",
        "address": "Valid Address",
        "phone": "not-a-number",
        "google_maps_url": "https://maps.google.com/?q=23.02,72.57"
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 400
    assert "phone" in res.get_json()["error"].lower()

def test_api_create_customer_rejection_missing_maps_url(client):
    payload = {
        "name": "Valid Name",
        "address": "Valid Address",
        "phone": "9825012345",
        "google_maps_url": ""
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 400
    assert "Google Maps Location URL is required" in res.get_json()["error"]

def test_api_create_customer_rejection_non_https_url(client):
    payload = {
        "name": "Valid Name",
        "address": "Valid Address",
        "phone": "9825012345",
        "google_maps_url": "http://maps.google.com/?q=23.02,72.57"
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 400
    assert "HTTPS" in res.get_json()["error"]

def test_api_create_customer_rejection_non_google_url(client):
    payload = {
        "name": "Valid Name",
        "address": "Valid Address",
        "phone": "9825012345",
        "google_maps_url": "https://bing.com/maps"
    }
    res = client.post('/api/master_customers', json=payload)
    assert res.status_code == 400
    assert "Google Maps" in res.get_json()["error"]

def test_api_create_customer_duplicate_phone_prevention(client):
    p1 = {
        "name": "Store Alpha",
        "address": "100 Alpha St",
        "phone": "9825011111",
        "google_maps_url": "https://maps.google.com/?q=23.01,72.51"
    }
    res1 = client.post('/api/master_customers', json=p1)
    assert res1.status_code == 201

    # Attempt to create another store with same phone
    p2 = {
        "name": "Store Beta",
        "address": "200 Beta St",
        "phone": "+91 98250 11111", # Same phone formatted differently
        "google_maps_url": "https://maps.google.com/?q=23.02,72.52"
    }
    res2 = client.post('/api/master_customers', json=p2)
    assert res2.status_code == 409
    assert "already registered" in res2.get_json()["error"].lower()

# ============================================================================
# 3. CUSTOMER EDIT API TESTS (PUT /api/master_customers/<id>)
# ============================================================================

def test_api_edit_customer_success(client):
    p = {
        "name": "Original Name",
        "address": "Original Address",
        "phone": "9825022222",
        "google_maps_url": "https://maps.app.goo.gl/original123"
    }
    res = client.post('/api/master_customers', json=p)
    cust_id = res.get_json()["customer"]["id"]

    # Update customer details
    update_payload = {
        "name": "Updated Name Cafe",
        "address": "Updated Address 99",
        "phone": "9825033333",
        "google_maps_url": "https://maps.google.com/?q=23.05,72.55",
        "lat": 23.05,
        "lng": 72.55
    }
    res_update = client.put(f'/api/master_customers/{cust_id}', json=update_payload)
    assert res_update.status_code == 200
    updated_cust = res_update.get_json()["customer"]
    assert updated_cust["name"] == "Updated Name Cafe"
    assert updated_cust["address"] == "Updated Address 99"
    assert updated_cust["phone"] == "9825033333"
    assert updated_cust["google_maps_url"] == "https://maps.google.com/?q=23.05,72.55"
    assert updated_cust["location_url"] == "https://maps.google.com/?q=23.05,72.55"
    assert updated_cust["lat"] == 23.05
    assert updated_cust["lng"] == 72.55

def test_api_edit_customer_rejection_on_invalid_data(client):
    p = {
        "name": "Test Customer",
        "address": "Test Address",
        "phone": "9825044444",
        "google_maps_url": "https://maps.app.goo.gl/valid123"
    }
    res = client.post('/api/master_customers', json=p)
    cust_id = res.get_json()["customer"]["id"]

    # Try clearing Google Maps URL
    bad_payload = {
        "name": "Test Customer",
        "address": "Test Address",
        "phone": "9825044444",
        "google_maps_url": ""
    }
    res_bad = client.put(f'/api/master_customers/{cust_id}', json=bad_payload)
    assert res_bad.status_code == 400
    assert "Google Maps Location URL is required" in res_bad.get_json()["error"]

def test_api_edit_legacy_customer_backward_compatibility(client):
    # Insert a legacy customer directly into DB without google_maps_url
    with app.app_context():
        legacy = MasterCustomer(
            name="Legacy Customer Ltd",
            address="Old Street, Industrial Area",
            phone=None,
            google_maps_url=None,
            location_url=None
        )
        db.session.add(legacy)
        db.session.commit()
        legacy_id = legacy.id

    # Verify GET returns customer safely
    res_get = client.get('/api/master_customers')
    assert res_get.status_code == 200
    data = res_get.get_json()
    leg_found = next((c for c in data["customers"] if c["id"] == legacy_id), None)
    assert leg_found is not None
    assert not leg_found["google_maps_url"]

    # Update legacy record by providing phone and google maps url
    update_payload = {
        "name": "Legacy Customer Ltd",
        "address": "Old Street, Industrial Area",
        "phone": "9825077777",
        "google_maps_url": "https://maps.google.com/?q=23.09,72.59"
    }
    res_up = client.put(f'/api/master_customers/{legacy_id}', json=update_payload)
    assert res_up.status_code == 200
    up_cust = res_up.get_json()["customer"]
    assert up_cust["google_maps_url"] == "https://maps.google.com/?q=23.09,72.59"
    assert up_cust["location_url"] == "https://maps.google.com/?q=23.09,72.59"

# ============================================================================
# 4. TEMPLATE INTEGRATION TEST (POST /api/templates/<id>/add_customer)
# ============================================================================

def test_api_add_customer_to_template_copies_maps_url(client):
    p = {
        "name": "Template Stop Customer",
        "address": "77 Ring Road",
        "phone": "9825088888",
        "google_maps_url": "https://maps.google.com/?q=23.06,72.56",
        "lat": 23.06,
        "lng": 72.56
    }
    res = client.post('/api/master_customers', json=p)
    cust_id = res.get_json()["customer"]["id"]

    # Add to template 101
    add_res = client.post('/api/templates/101/add_customer', json={"customer_id": cust_id})
    assert add_res.status_code == 200

    # Inspect template stops
    with app.app_context():
        tpl = db.session.get(SavedTemplate, 101)
        stops = json.loads(tpl.customers_json)
        stop = next((s for s in stops if s.get("name") == "Template Stop Customer"), None)
        assert stop is not None
        assert stop["location_url"] == "https://maps.google.com/?q=23.06,72.56"
        assert stop["google_maps_url"] == "https://maps.google.com/?q=23.06,72.56"
        assert stop["phone"] == "9825088888"

# ============================================================================
# 5. BULK IMPORT: EXCEL (.xlsx, .xls)
# ============================================================================

def create_excel_bytes(rows, headers=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    if headers is None:
        headers = ["Customer Name", "Address", "Phone Number", "Google Maps Location URL", "Latitude", "Longitude"]
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

def test_excel_bulk_import_full_workflow(client):
    rows = [
        ["Bulk Cafe A", "101 High St", "9825111111", "https://maps.google.com/?q=23.01,72.51", 23.01, 72.51],
        ["Bulk Cafe B", "102 High St", "9825222222", "https://maps.app.goo.gl/shareB", "", ""], # coords optional
        ["Invalid URL Store", "103 High St", "9825333333", "https://badsite.com", "", ""], # invalid URL
        ["Duplicate Phone Store", "104 High St", "9825111111", "https://maps.google.com/?q=23.04,72.54", "", ""] # dup phone with row 1
    ]
    file_bytes = create_excel_bytes(rows)

    # Preview stage
    preview_res = client.post(
        '/api/master_customers/import_preview',
        data={'file': (file_bytes, 'customers.xlsx')},
        content_type='multipart/form-data'
    )
    assert preview_res.status_code == 200
    pdata = preview_res.get_json()
    assert pdata["success"] is True
    assert pdata["total_detected"] == 4
    assert pdata["valid_count"] == 2 # Row 1 and Row 2
    assert pdata["invalid_count"] == 1 # Row 3
    assert pdata["duplicate_count"] == 1 # Row 4
    preview_id = pdata["preview_id"]

    # Verify preview rows contain google_maps_url
    assert pdata["rows"][0]["google_maps_url"] == "https://maps.google.com/?q=23.01,72.51"
    assert pdata["rows"][1]["google_maps_url"] == "https://maps.app.goo.gl/shareB"

    # Confirm import stage
    confirm_res = client.post(
        '/api/master_customers/import_confirm',
        json={'preview_id': preview_id, 'skip_duplicates': True}
    )
    assert confirm_res.status_code == 200
    cdata = confirm_res.get_json()
    assert cdata["imported"] == 2
    assert cdata["skipped_duplicates"] == 1
    assert cdata["skipped_invalid"] == 1

    # Verify database has the 2 imported customers
    with app.app_context():
        c_a = MasterCustomer.query.filter_by(name="Bulk Cafe A").first()
        assert c_a is not None
        assert c_a.google_maps_url == "https://maps.google.com/?q=23.01,72.51"
        assert c_a.location_url == "https://maps.google.com/?q=23.01,72.51"

        c_b = MasterCustomer.query.filter_by(name="Bulk Cafe B").first()
        assert c_b is not None
        assert c_b.google_maps_url == "https://maps.app.goo.gl/shareB"

def test_excel_bulk_import_missing_mandatory_column_rejected(client):
    # Missing Google Maps Location URL column completely
    headers = ["Customer Name", "Address", "Phone Number", "Latitude", "Longitude"]
    rows = [["Test Cafe", "123 St", "9825123456", 23.0, 72.0]]
    file_bytes = create_excel_bytes(rows, headers=headers)

    res = client.post(
        '/api/master_customers/import_preview',
        data={'file': (file_bytes, 'missing_column.xlsx')},
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    data = res.get_json()
    assert "missing mandatory column" in data["error"].lower()
    assert "Google Maps Location URL" in data["error"]

def test_excel_bulk_import_header_synonyms_resilience(client):
    # Synonyms: Full Name, Full Address, Mobile, Location Link, Lat, Lng
    headers = ["Full Name *", "Delivery Address", "Mobile No.", "Location Link (Mandatory)", "Lat", "Lng"]
    rows = [["Synonym Eatery", "90 Market Lane", "+91 9988776655", "https://maps.google.com/?q=23.1,72.6", 23.1, 72.6]]
    file_bytes = create_excel_bytes(rows, headers=headers)

    res = client.post(
        '/api/master_customers/import_preview',
        data={'file': (file_bytes, 'synonyms.xlsx')},
        content_type='multipart/form-data'
    )
    assert res.status_code == 200
    pdata = res.get_json()
    assert pdata["valid_count"] == 1
    assert pdata["rows"][0]["name"] == "Synonym Eatery"
    assert pdata["rows"][0]["phone"] == "+91 9988776655"
    assert pdata["rows"][0]["google_maps_url"] == "https://maps.google.com/?q=23.1,72.6"

# ============================================================================
# 6. BULK IMPORT: WORD (.docx)
# ============================================================================

def create_docx_bytes(rows, headers=None):
    doc = Document()
    doc.add_heading("Customer Roster", 0)
    if headers is None:
        headers = ["Customer Name", "Address", "Phone Number", "Google Maps Location URL", "Latitude", "Longitude"]
    table = doc.add_table(rows=1, cols=len(headers))
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
    for r in rows:
        row_cells = table.add_row().cells
        for i, val in enumerate(r):
            row_cells[i].text = str(val) if val is not None else ""
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf

def test_docx_bulk_import_success(client):
    rows = [
        ["Word Cafe 1", "300 Word Plaza", "9825444111", "https://maps.app.goo.gl/word1", "23.011", "72.511"],
        ["Word Cafe 2", "301 Word Plaza", "9825444222", "https://maps.google.com/?q=23.022,72.522", "", ""]
    ]
    file_bytes = create_docx_bytes(rows)

    preview_res = client.post(
        '/api/master_customers/import_preview',
        data={'file': (file_bytes, 'customers.docx')},
        content_type='multipart/form-data'
    )
    assert preview_res.status_code == 200
    pdata = preview_res.get_json()
    assert pdata["total_detected"] == 2
    assert pdata["valid_count"] == 2

    # Confirm import
    confirm_res = client.post(
        '/api/master_customers/import_confirm',
        json={'preview_id': pdata["preview_id"], 'skip_duplicates': True}
    )
    assert confirm_res.status_code == 200
    assert confirm_res.get_json()["imported"] == 2

def test_docx_rejection_missing_mandatory_field(client):
    # Row 1 is missing phone, Row 2 is missing URL
    rows = [
        ["Word Bad 1", "300 Word Plaza", "", "https://maps.app.goo.gl/word1", "", ""],
        ["Word Bad 2", "301 Word Plaza", "9825444333", "", "", ""]
    ]
    file_bytes = create_docx_bytes(rows)

    preview_res = client.post(
        '/api/master_customers/import_preview',
        data={'file': (file_bytes, 'bad.docx')},
        content_type='multipart/form-data'
    )
    assert preview_res.status_code == 200
    pdata = preview_res.get_json()
    assert pdata["valid_count"] == 0
    assert pdata["invalid_count"] == 2

# ============================================================================
# 7. BULK IMPORT: CSV (.csv) & REJECTION OF LEGACY .doc
# ============================================================================

def test_csv_bulk_import_success(client):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Customer Name", "Address", "Phone Number", "Google Maps Location URL", "Latitude", "Longitude"])
    writer.writerow(["CSV Stop 1", "12 CSV Street", "9825999001", "https://maps.google.com/?q=23.05,72.55", "23.05", "72.55"])
    writer.writerow(["CSV Stop 2", "14 CSV Street", "9825999002", "https://maps.app.goo.gl/csvStop2", "", ""])
    csv_bytes = io.BytesIO(output.getvalue().encode('utf-8'))

    preview_res = client.post(
        '/api/master_customers/import_preview',
        data={'file': (csv_bytes, 'customers.csv')},
        content_type='multipart/form-data'
    )
    assert preview_res.status_code == 200
    pdata = preview_res.get_json()
    assert pdata["total_detected"] == 2
    assert pdata["valid_count"] == 2

def test_rejection_of_legacy_doc_file(client):
    fake_doc_bytes = io.BytesIO(b"Legacy Word Binary Format")
    res = client.post(
        '/api/master_customers/import_preview',
        data={'file': (fake_doc_bytes, 'legacy_customers.doc')},
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    assert "Legacy .doc format is not supported" in res.get_json()["error"]

# ============================================================================
# 8. DOWNLOADABLE ERROR REPORT & SAMPLE TEMPLATES
# ============================================================================

def test_download_error_report_csv(client):
    rows = [
        ["Valid 1", "Addr 1", "9825888001", "https://maps.google.com/?q=23.01,72.51", "", ""],
        ["Invalid URL", "Addr 2", "9825888002", "http://insecure-maps.com", "", ""]
    ]
    file_bytes = create_excel_bytes(rows)

    preview_res = client.post(
        '/api/master_customers/import_preview',
        data={'file': (file_bytes, 'test_err.xlsx')},
        content_type='multipart/form-data'
    )
    preview_id = preview_res.get_json()["preview_id"]

    # Download error report
    err_rep_res = client.get(f'/api/master_customers/import_error_report/{preview_id}')
    assert err_rep_res.status_code == 200
    assert "text/csv" in err_rep_res.content_type
    csv_content = err_rep_res.get_data(as_text=True)
    assert ("Row #" in csv_content or "Row Number" in csv_content)
    assert "Customer Name" in csv_content
    assert "Invalid URL" in csv_content
    assert "HTTPS" in csv_content or "Google Maps" in csv_content

def test_sample_excel_template_structure(client):
    res = client.get('/api/master_customers/sample_excel')
    assert res.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res.content_type
    
    # Read downloaded excel in memory
    wb = openpyxl.load_workbook(io.BytesIO(res.data))
    ws = wb.active
    headers = [cell.value for cell in ws[1]]
    assert "Customer Name *" in headers
    assert "Address *" in headers
    assert "Phone Number *" in headers
    assert "Google Maps Location URL *" in headers
    assert "Latitude (Optional)" in headers
    assert "Longitude (Optional)" in headers
    
    # Check sample row
    sample_row = [cell.value for cell in ws[2]]
    assert sample_row[0] == "Green Leaf Cafe"
    assert sample_row[2] == "9876543210"
    assert "https://maps.google.com/" in str(sample_row[3])

def test_sample_word_template_structure(client):
    res = client.get('/api/master_customers/sample_word')
    assert res.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in res.content_type

    doc = Document(io.BytesIO(res.data))
    assert len(doc.tables) >= 1
    table = doc.tables[0]
    hdr_cells = [cell.text.strip() for cell in table.rows[0].cells]
    assert "Customer Name *" in hdr_cells
    assert "Address *" in hdr_cells
    assert "Phone Number *" in hdr_cells
    assert "Google Maps Location URL *" in hdr_cells
    assert "Latitude (Optional)" in hdr_cells
    assert "Longitude (Optional)" in hdr_cells

    row_cells = [cell.text.strip() for cell in table.rows[1].cells]
    assert row_cells[0] == "Green Leaf Cafe"
    assert row_cells[2] == "9876543210"

# ============================================================================
# 9. ROUTE GENERATION & GEOCODING WORKFLOW COMPATIBILITY
# ============================================================================

def test_read_data_file_maps_url_support():
    # Verify read_data_file preserves location_url and google_maps_url
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "Address", "Phone", "Google Maps URL", "Latitude", "Longitude"])
    ws.append(["Route Stop A", "200 Route Ave", "9825123123", "https://maps.google.com/?q=23.01,72.51", 23.01, 72.51])
    
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tf:
        tmp_name = tf.name
        wb.save(tmp_name)

    try:
        customers = read_data_file(tmp_name)
        assert len(customers) == 1
        stop = customers[0]
        assert stop["name"] == "Route Stop A"
        assert stop["phone"] == "9825123123"
        assert stop["location_url"] == "https://maps.google.com/?q=23.01,72.51"
        assert stop["google_maps_url"] == "https://maps.google.com/?q=23.01,72.51"
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
