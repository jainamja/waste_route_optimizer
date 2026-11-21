import pytest
import io
import json
import openpyxl
import docx
from waste_route_optimizer import app, db, User, Customer, SavedTemplate, MasterCustomer
from werkzeug.security import generate_password_hash

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        # Clean master_customers for a clean test run
        MasterCustomer.query.delete()

        admin = User.query.filter_by(role='ADMIN').first()
        if not admin:
            admin = User(
                username='admin_test',
                password_hash=generate_password_hash('adminpass123'),
                role='ADMIN',
                name='Admin Test'
            )
            db.session.add(admin)
            db.session.commit()

        driver = User.query.filter_by(username='driver_test').first()
        if not driver:
            driver = User(
                username='driver_test',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Driver Test',
                truck_id=1
            )
            db.session.add(driver)
            db.session.commit()

        # Templates
        t5 = db.session.get(SavedTemplate, 5)
        if not t5:
            t5 = SavedTemplate(id=5, name='Tuesday Route', customers_json='[]', is_assigned_instance=False)
            db.session.add(t5)
        else:
            t5.customers_json = '[]'

        t8 = db.session.get(SavedTemplate, 8)
        if not t8:
            t8 = SavedTemplate(id=8, name='Thursday Route', customers_json='[]', is_assigned_instance=False)
            db.session.add(t8)
        else:
            t8.customers_json = '[]'

        db.session.commit()

    with app.test_client() as client:
        yield client

def login_as_admin(client):
    with app.app_context():
        admin = User.query.filter_by(role='ADMIN').first()
        admin_id = admin.id
    with client.session_transaction() as sess:
        sess['user_id'] = admin_id

def login_as_driver(client):
    with app.app_context():
        driver = User.query.filter_by(role='DRIVER').first()
        driver_id = driver.id
    with client.session_transaction() as sess:
        sess['user_id'] = driver_id


def create_excel_bytes(rows, headers=None):
    if headers is None:
        headers = ['Customer Name', 'Address', 'Phone', 'Latitude', 'Longitude', 'Location URL', 'Deliver Bag']
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def create_word_bytes(rows, headers=None):
    if headers is None:
        headers = ['Customer Name', 'Address', 'Phone', 'Latitude', 'Longitude', 'Location URL', 'Deliver Bag']
    doc = docx.Document()
    doc.add_heading("Customer Import", level=1)
    table = doc.add_table(rows=1, cols=len(headers))
    for idx, h in enumerate(headers):
        table.rows[0].cells[idx].text = h
    for r in rows:
        row_cells = table.add_row().cells
        for idx, val in enumerate(r):
            row_cells[idx].text = str(val if val is not None else '')
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ============================================================================
# 1. AUTH & PERMISSIONS TESTS
# ============================================================================
def test_unauthorized_bulk_import(client):
    """Req 14: Verify unauthorized import requests are rejected."""
    # 1. Unauthenticated -> 401
    res = client.post('/api/master_customers/import_preview', data={})
    assert res.status_code == 401

    res = client.post('/api/master_customers/import_confirm', json={'rows': []})
    assert res.status_code == 401

    # 2. Driver role -> 403 Forbidden
    login_as_driver(client)
    res = client.post('/api/master_customers/import_preview', data={})
    assert res.status_code == 403

    res = client.post('/api/master_customers/import_confirm', json={'rows': []})
    assert res.status_code == 403


# ============================================================================
# 2. SAMPLE TEMPLATE DOWNLOADS
# ============================================================================
def test_sample_template_downloads(client):
    """Req 21 & 22: Sample Excel and Word templates can be downloaded and parsed."""
    login_as_admin(client)

    # 1. Excel Sample
    res_xl = client.get('/api/master_customers/sample_excel')
    assert res_xl.status_code == 200
    assert 'application/vnd.openxmlformats' in res_xl.content_type
    # Parse downloaded excel to verify it works
    wb = openpyxl.load_workbook(io.BytesIO(res_xl.data))
    sheet = wb.worksheets[0]
    headers = [c.value for c in sheet[1]]
    assert 'Customer Name' in headers
    assert 'Address' in headers

    # 2. Word Sample
    res_wd = client.get('/api/master_customers/sample_word')
    assert res_wd.status_code == 200
    assert 'application/vnd.openxmlformats' in res_wd.content_type
    doc = docx.Document(io.BytesIO(res_wd.data))
    assert len(doc.tables) >= 1
    table_headers = [c.text for c in doc.tables[0].rows[0].cells]
    assert 'Customer Name' in table_headers
    assert 'Address' in table_headers


# ============================================================================
# 3. EXCEL IMPORT & PREVIEW TESTS
# ============================================================================
def test_successful_excel_preview_and_confirm(client):
    """Req 1 & 3: Successful Excel import with multiple customers."""
    login_as_admin(client)

    rows = [
        ['Cafe Mocha', '101 Marine Drive', '9876543210', 23.01, 72.56, '', 'Yes'],
        ['Green Mart', '102 Marine Drive', '9876543211', 23.02, 72.57, '', 'No'],
        ['Blue Lagoon Resort', '103 Marine Drive', '9876543212', 23.03, 72.58, '', 'Yes']
    ]
    excel_buf = create_excel_bytes(rows)

    # Preview
    data = {'file': (excel_buf, 'customers.xlsx')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['success'] is True
    assert preview['total_detected'] == 3
    assert preview['valid_count'] == 3
    assert preview['duplicate_count'] == 0
    assert preview['invalid_count'] == 0
    assert len(preview['rows']) == 3
    assert preview['preview_id'] is not None

    # Confirm Import
    confirm_res = client.post('/api/master_customers/import_confirm', json={'preview_id': preview['preview_id']})
    assert confirm_res.status_code == 200
    res_json = confirm_res.get_json()
    assert res_json['success'] is True
    assert res_json['imported'] == 3
    assert res_json['skipped_duplicates'] == 0

    # Verify records in database
    with app.app_context():
        custs = MasterCustomer.query.all()
        assert len(custs) == 3
        names = [c.name for c in custs]
        assert 'Cafe Mocha' in names
        assert 'Green Mart' in names
        assert 'Blue Lagoon Resort' in names


# ============================================================================
# 4. WORD (.DOCX) IMPORT & PREVIEW TESTS
# ============================================================================
def test_successful_word_preview_and_confirm(client):
    """Req 2: Successful Word table import (.docx)."""
    login_as_admin(client)

    rows = [
        ['Apex Heights', '77 S.G. Highway', '9988776655', 23.08, 72.51, '', 'Yes'],
        ['Zenith Towers', '88 S.G. Highway', '9988776656', 23.09, 72.52, '', 'No']
    ]
    word_buf = create_word_bytes(rows)

    data = {'file': (word_buf, 'customers.docx')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['total_detected'] == 2
    assert preview['valid_count'] == 2

    # Confirm Import
    confirm_res = client.post('/api/master_customers/import_confirm', json={'preview_id': preview['preview_id']})
    assert confirm_res.status_code == 200
    assert confirm_res.get_json()['imported'] == 2

    with app.app_context():
        assert MasterCustomer.query.filter_by(name='Apex Heights').count() == 1
        assert MasterCustomer.query.filter_by(name='Zenith Towers').count() == 1


# ============================================================================
# 5. VALIDATION & ERROR HANDLING TESTS
# ============================================================================
def test_missing_required_columns(client):
    """Req 4: Missing required columns (Name or Address)."""
    login_as_admin(client)

    # Missing Address column
    headers = ['Customer Name', 'Phone', 'Latitude']
    rows = [['John Doe', '1234567890', 23.0]]
    excel_buf = create_excel_bytes(rows, headers=headers)

    res = client.post('/api/master_customers/import_preview', data={'file': (excel_buf, 'missing_cols.xlsx')}, content_type='multipart/form-data')
    assert res.status_code == 400
    assert 'Could not identify required' in res.get_json()['error']


def test_missing_required_values_in_rows(client):
    """Req 5: Missing required values in individual rows."""
    login_as_admin(client)

    rows = [
        ['Valid Customer', 'Valid Address', '1234567890', 23.0, 72.0, '', 'No'],
        ['', 'Address Without Name', '1234567891', 23.0, 72.0, '', 'No'],
        ['Name Without Address', '', '1234567892', 23.0, 72.0, '', 'No']
    ]
    excel_buf = create_excel_bytes(rows)

    res = client.post('/api/master_customers/import_preview', data={'file': (excel_buf, 'missing_vals.xlsx')}, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['total_detected'] == 3
    assert preview['valid_count'] == 1
    assert preview['invalid_count'] == 2


def test_invalid_coordinates(client):
    """Req 6: Invalid coordinates (latitude / longitude out of range)."""
    login_as_admin(client)

    rows = [
        ['Customer Lat Out Of Range', '123 Test St', '1234567890', 95.0, 72.0, '', 'No'], # Lat > 90
        ['Customer Lng Out Of Range', '124 Test St', '1234567891', 23.0, -195.0, '', 'No'], # Lng < -180
        ['Customer Bad Numeric Lat', '125 Test St', '1234567892', 'NOT_A_NUMBER', 72.0, '', 'No']
    ]
    excel_buf = create_excel_bytes(rows)

    res = client.post('/api/master_customers/import_preview', data={'file': (excel_buf, 'coords.xlsx')}, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['invalid_count'] == 3
    assert preview['valid_count'] == 0


def test_empty_spreadsheet_rows_ignored(client):
    """Req 7: Completely empty rows are ignored."""
    login_as_admin(client)

    rows = [
        ['Customer 1', 'Address 1', '1234567890', 23.0, 72.0, '', 'No'],
        [None, None, None, None, None, None, None],
        ['', '', '', '', '', '', ''],
        ['Customer 2', 'Address 2', '1234567891', 23.1, 72.1, '', 'No']
    ]
    excel_buf = create_excel_bytes(rows)

    res = client.post('/api/master_customers/import_preview', data={'file': (excel_buf, 'empty_rows.xlsx')}, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['total_detected'] == 2
    assert preview['valid_count'] == 2


# ============================================================================
# 6. DUPLICATE HANDLING TESTS
# ============================================================================
def test_duplicates_in_database_and_within_file(client):
    """Req 8 & 9: Duplicates already in master list and within same file."""
    login_as_admin(client)

    # Seed one existing master customer
    with app.app_context():
        db.session.add(MasterCustomer(
            id=1,
            name='Existing Store',
            address='100 Old Rd',
            phone='9898989898',
            customer_status='ACTIVE'
        ))
        db.session.commit()

    rows = [
        # Duplicate of existing in DB
        ['Existing Store', '100 Old Rd', '9898989898', 23.0, 72.0, '', 'No'],
        # New customer
        ['Brand New Customer', '200 New Rd', '9111111111', 23.1, 72.1, '', 'No'],
        # Duplicate within file of Brand New Customer
        ['brand new customer', '200 new rd', '9111111111', 23.1, 72.1, '', 'No']
    ]
    excel_buf = create_excel_bytes(rows)

    res = client.post('/api/master_customers/import_preview', data={'file': (excel_buf, 'dups.xlsx')}, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['total_detected'] == 3
    assert preview['valid_count'] == 1
    assert preview['duplicate_count'] == 2

    # Confirm Import: only 1 new customer imported, 2 duplicates skipped
    confirm_res = client.post('/api/master_customers/import_confirm', json={'preview_id': preview['preview_id']})
    assert confirm_res.status_code == 200
    res_data = confirm_res.get_json()
    assert res_data['imported'] == 1
    assert res_data['skipped_duplicates'] == 2


def test_similar_names_with_different_addresses(client):
    """Req 10: Similar customer names with different addresses are NOT duplicates."""
    login_as_admin(client)

    rows = [
        ['Cafe Coffee Day', 'Location A, MG Road', '9000000001', 23.0, 72.0, '', 'No'],
        ['Cafe Coffee Day', 'Location B, SG Highway', '9000000002', 23.1, 72.1, '', 'No']
    ]
    excel_buf = create_excel_bytes(rows)

    res = client.post('/api/master_customers/import_preview', data={'file': (excel_buf, 'similar_names.xlsx')}, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['valid_count'] == 2
    assert preview['duplicate_count'] == 0


# ============================================================================
# 7. SECURITY & FORMAT RESTRICTIONS
# ============================================================================
def test_unsupported_and_legacy_formats(client):
    """Req 11: Unsupported formats (.pdf, .doc) rejected with clear messages."""
    login_as_admin(client)

    # PDF rejection
    pdf_data = {'file': (io.BytesIO(b'%PDF-1.4...'), 'test.pdf')}
    res_pdf = client.post('/api/master_customers/import_preview', data=pdf_data, content_type='multipart/form-data')
    assert res_pdf.status_code == 400
    assert 'Unsupported file format' in res_pdf.get_json()['error']

    # Legacy .doc rejection with specific guidance
    doc_data = {'file': (io.BytesIO(b'fake doc binary'), 'test.doc')}
    res_doc = client.post('/api/master_customers/import_preview', data=doc_data, content_type='multipart/form-data')
    assert res_doc.status_code == 400
    assert 'Legacy .doc format is not supported' in res_doc.get_json()['error']


def test_malformed_files(client):
    """Req 12 & 13: Malformed Excel and Word files handled gracefully."""
    login_as_admin(client)

    corrupt_excel = {'file': (io.BytesIO(b'NOT A REAL EXCEL FILE'), 'corrupt.xlsx')}
    res_xl = client.post('/api/master_customers/import_preview', data=corrupt_excel, content_type='multipart/form-data')
    assert res_xl.status_code == 400
    assert 'Failed to read Excel' in res_xl.get_json()['error']

    corrupt_word = {'file': (io.BytesIO(b'NOT A REAL WORD FILE'), 'corrupt.docx')}
    res_wd = client.post('/api/master_customers/import_preview', data=corrupt_word, content_type='multipart/form-data')
    assert res_wd.status_code == 400
    assert 'Failed to read Word' in res_wd.get_json()['error']


def test_word_document_without_table(client):
    """Req 13: Word document with arbitrary paragraphs and no table is rejected cleanly."""
    login_as_admin(client)

    doc = docx.Document()
    doc.add_paragraph("This is just an arbitrary paragraph with no customer table.")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    data = {'file': (buf, 'no_table.docx')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 400
    assert 'No table found' in res.get_json()['error']


# ============================================================================
# 8. FINAL END-TO-END ACCEPTANCE WORKFLOW
# ============================================================================
def test_complete_acceptance_workflow_excel(client):
    """
    Section 13 Final Acceptance Test:
    1. Upload Excel file with 100 customer records.
    2. Preview all 100 records (valid, duplicates, invalid).
    3. Confirm import.
    4. Valid new customers appear in Master Customer List.
    5. Add imported customer to Tuesday Route (#5) AND Thursday Route (#8).
    6. Verify single master customer record maintained.
    7. Existing assigned routes and driver progress remain unchanged.
    """
    login_as_admin(client)

    # Generate 100 customer rows:
    # 90 valid new
    # 5 duplicates of earlier rows
    # 5 invalid (blank names/invalid lat)
    rows = []
    for i in range(1, 91):
        rows.append([f'Client {i}', f'{i} Express Way, Sector {i%10 + 1}', f'98000000{i:02d}', 23.0 + i*0.001, 72.5 + i*0.001, '', 'Yes' if i%2 == 0 else 'No'])

    # 5 duplicate rows
    for i in range(1, 6):
        rows.append([f'Client {i}', f'{i} Express Way, Sector {i%10 + 1}', f'98000000{i:02d}', 23.0 + i*0.001, 72.5 + i*0.001, '', 'No'])

    # 5 invalid rows
    rows.append(['', 'Address With Missing Name', '9100000001', 23.0, 72.0, '', 'No'])
    rows.append(['Missing Address Client', '', '9100000002', 23.0, 72.0, '', 'No'])
    rows.append(['Invalid Lat Client', '100 Bad Lat Rd', '9100000003', 195.0, 72.0, '', 'No'])
    rows.append(['Invalid Lng Client', '101 Bad Lng Rd', '9100000004', 23.0, -220.0, '', 'No'])
    rows.append(['', '', '9100000005', 23.0, 72.0, '', 'No'])

    assert len(rows) == 100

    excel_buf = create_excel_bytes(rows)
    data = {'file': (excel_buf, '100_customers.xlsx')}

    # 1. Preview
    preview_res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert preview_res.status_code == 200
    p = preview_res.get_json()
    assert p['total_detected'] == 100
    assert p['valid_count'] == 90
    assert p['duplicate_count'] == 5
    assert p['invalid_count'] == 5

    # 2. Confirm import
    confirm_res = client.post('/api/master_customers/import_confirm', json={'preview_id': p['preview_id']})
    assert confirm_res.status_code == 200
    c_data = confirm_res.get_json()
    assert c_data['imported'] == 90
    assert c_data['skipped_duplicates'] == 5
    assert c_data['skipped_invalid'] == 5

    # 3. Master Customer List query reflects 90 imported customers
    list_res = client.get('/api/master_customers?limit=100')
    assert list_res.status_code == 200
    assert list_res.get_json()['total'] == 90

    # Pick Client 1
    with app.app_context():
        c1 = MasterCustomer.query.filter_by(name='Client 1').first()
        assert c1 is not None
        c1_id = c1.id

    # 4. Add Client 1 to Tuesday Route (#5)
    t5_res = client.post('/api/templates/5/add_customer', json={'customer_id': c1_id})
    assert t5_res.status_code == 200

    # 5. Add Client 1 to Thursday Route (#8)
    t8_res = client.post('/api/templates/8/add_customer', json={'customer_id': c1_id})
    assert t8_res.status_code == 200

    # 6. Verify single master customer record
    with app.app_context():
        assert MasterCustomer.query.filter_by(name='Client 1').count() == 1

        t5 = db.session.get(SavedTemplate, 5)
        t5_stops = json.loads(t5.customers_json or '[]')
        assert any(s.get('master_customer_id') == c1_id for s in t5_stops)

        t8 = db.session.get(SavedTemplate, 8)
        t8_stops = json.loads(t8.customers_json or '[]')
        assert any(s.get('master_customer_id') == c1_id for s in t8_stops)


def test_complete_acceptance_workflow_word(client):
    """Section 13 Final Acceptance Test with Word document."""
    login_as_admin(client)

    rows = [
        ['Word Client Alpha', '500 Alpha Plaza', '9700000001', 23.05, 72.55, '', 'Yes'],
        ['Word Client Beta', '600 Beta Center', '9700000002', 23.06, 72.56, '', 'No']
    ]
    word_buf = create_word_bytes(rows)

    preview_res = client.post('/api/master_customers/import_preview', data={'file': (word_buf, 'batch.docx')}, content_type='multipart/form-data')
    assert preview_res.status_code == 200
    p = preview_res.get_json()
    assert p['valid_count'] == 2

    confirm_res = client.post('/api/master_customers/import_confirm', json={'preview_id': p['preview_id']})
    assert confirm_res.status_code == 200
    assert confirm_res.get_json()['imported'] == 2

    # Add Word Client Alpha to Tuesday Route
    with app.app_context():
        c = MasterCustomer.query.filter_by(name='Word Client Alpha').first()
        c_id = c.id

    t5_res = client.post('/api/templates/5/add_customer', json={'customer_id': c_id})
    assert t5_res.status_code == 200
