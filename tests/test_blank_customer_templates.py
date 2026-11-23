import pytest
import io
import csv
import json
import openpyxl
import docx
from waste_route_optimizer import app, db, User, MasterCustomer, SavedTemplate
from werkzeug.security import generate_password_hash

EXPECTED_HEADERS = [
    'Customer Name',
    'Address',
    'Phone Number',
    'Google Maps Location URL',
    'Latitude',
    'Longitude'
]

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        MasterCustomer.query.delete()

        admin = User.query.filter_by(role='ADMIN').first()
        if not admin:
            admin = User(
                username='admin_test_tmpl',
                password_hash=generate_password_hash('adminpass123'),
                role='ADMIN',
                name='Admin Test'
            )
            db.session.add(admin)
            db.session.commit()

        driver = User.query.filter_by(username='driver_test_tmpl').first()
        if not driver:
            driver = User(
                username='driver_test_tmpl',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Driver Test',
                truck_id=1
            )
            db.session.add(driver)
            db.session.commit()

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


# ==============================================================================
# 1. EXCEL TEMPLATE TESTS
# ==============================================================================

def test_download_excel_template_headers_and_filename(client):
    """Test GET /api/master_customers/template/excel returns 200 with correct filename and headers."""
    login_as_admin(client)
    res = client.get('/api/master_customers/template/excel')
    assert res.status_code == 200
    assert 'attachment' in res.headers.get('Content-Disposition', '')
    assert 'TrashTrekyx_Customer_Template.xlsx' in res.headers.get('Content-Disposition', '')
    assert 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in res.content_type

    wb = openpyxl.load_workbook(io.BytesIO(res.data))
    ws = wb.active
    assert ws.title == 'Customers'

    # Check top row has exact 6 headers
    actual_headers = [cell.value for cell in ws[1]]
    assert actual_headers == EXPECTED_HEADERS

    # Check freeze panes set on row 2
    assert ws.freeze_panes == 'A2'

    # Check column styling and comments
    for i in range(1, 5):
        cell = ws.cell(row=1, column=i)
        assert cell.fill.start_color.rgb == '001D4ED8' or '1D4ED8' in str(cell.fill.start_color.rgb)
        assert cell.comment is not None
        assert 'MANDATORY' in cell.comment.text

    for i in range(5, 7):
        cell = ws.cell(row=1, column=i)
        assert cell.fill.start_color.rgb == '0064748B' or '64748B' in str(cell.fill.start_color.rgb)
        assert cell.comment is not None
        assert 'OPTIONAL' in cell.comment.text


def test_excel_template_has_no_fake_customer_records(client):
    """Excel template must have blank entry rows and NO fake customer data."""
    login_as_admin(client)
    res = client.get('/api/master_customers/template/excel')
    wb = openpyxl.load_workbook(io.BytesIO(res.data))
    ws = wb.active

    # Rows 2 to 11 are formatted blank rows
    for r in range(2, ws.max_row + 1):
        row_vals = [ws.cell(row=r, column=c).value for c in range(1, 7)]
        assert all(v is None or str(v).strip() == '' for v in row_vals), f"Row {r} has unexpected data: {row_vals}"


def test_excel_template_empty_upload_rejected_cleanly(client):
    """Uploading the unedited blank Excel template should reject cleanly with 400 (no data rows)."""
    login_as_admin(client)
    res_dl = client.get('/api/master_customers/template/excel')
    excel_bytes = res_dl.data

    data = {'file': (io.BytesIO(excel_bytes), 'TrashTrekyx_Customer_Template.xlsx')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 400
    res_data = res.get_json()
    assert res_data['success'] is False
    assert 'No data rows found' in res_data['error']


def test_excel_template_roundtrip_import(client):
    """Fill downloaded Excel template with customers and import successfully via preview & confirm."""
    login_as_admin(client)
    res_dl = client.get('/api/master_customers/template/excel')
    wb = openpyxl.load_workbook(io.BytesIO(res_dl.data))
    ws = wb.active

    # Add 2 valid customers
    ws.cell(row=2, column=1, value='Alpha Biotech')
    ws.cell(row=2, column=2, value='100 Science Park, Ahmedabad')
    ws.cell(row=2, column=3, value='9876543201')
    ws.cell(row=2, column=4, value='https://maps.google.com/?q=23.0300,72.5800')
    ws.cell(row=2, column=5, value=23.0300)
    ws.cell(row=2, column=6, value=72.5800)

    ws.cell(row=3, column=1, value='Beta Logistics')
    ws.cell(row=3, column=2, value='200 Transport Hub, Ahmedabad')
    ws.cell(row=3, column=3, value='9876543202')
    ws.cell(row=3, column=4, value='https://maps.google.com/?q=23.0400,72.5900')
    # Lat/Lng left blank (optional)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    data = {'file': (buf, 'TrashTrekyx_Customer_Template.xlsx')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['success'] is True
    assert preview['total_detected'] == 2
    assert preview['valid_count'] == 2
    assert preview['ready_to_import_count'] == 2
    assert preview['rows'][0]['name'] == 'Alpha Biotech'
    assert preview['rows'][1]['name'] == 'Beta Logistics'
    # Coordinates auto-extracted for Beta Logistics from Google Maps URL
    assert preview['rows'][1]['lat'] == 23.0400
    assert preview['rows'][1]['lng'] == 72.5900

    # Confirm import
    confirm_res = client.post('/api/master_customers/import_confirm', json={
        'preview_id': preview['preview_id'],
        'destination_template_id': None
    })
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.get_json()
    assert confirm_data['success'] is True
    assert confirm_data['imported'] == 2

    with app.app_context():
        c1 = MasterCustomer.query.filter_by(name='Alpha Biotech').first()
        c2 = MasterCustomer.query.filter_by(name='Beta Logistics').first()
        assert c1 is not None
        assert c2 is not None


# ==============================================================================
# 2. WORD TEMPLATE TESTS
# ==============================================================================

def test_download_word_template_headers_and_filename(client):
    """Test GET /api/master_customers/template/word returns 200 with correct filename and headers."""
    login_as_admin(client)
    res = client.get('/api/master_customers/template/word')
    assert res.status_code == 200
    assert 'attachment' in res.headers.get('Content-Disposition', '')
    assert 'TrashTrekyx_Customer_Template.docx' in res.headers.get('Content-Disposition', '')
    assert 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in res.content_type

    doc = docx.Document(io.BytesIO(res.data))
    assert len(doc.tables) >= 1
    tbl = doc.tables[0]

    # Verify header row
    actual_headers = [c.text.strip() for c in tbl.rows[0].cells]
    assert actual_headers == EXPECTED_HEADERS

    # Verify instructions paragraph
    doc_text = '\n'.join(p.text for p in doc.paragraphs)
    assert 'TrashTrekyx — Blank Customer Import Template' in doc_text
    assert 'Customer Name' in doc_text
    assert 'mandatory' in doc_text.lower()
    assert 'optional' in doc_text.lower()
    assert 'Google Maps' in doc_text


def test_word_template_has_no_fake_customer_records(client):
    """Word template must have blank entry rows and NO fake customer data."""
    login_as_admin(client)
    res = client.get('/api/master_customers/template/word')
    doc = docx.Document(io.BytesIO(res.data))
    tbl = doc.tables[0]

    assert len(tbl.rows) > 1 # Has blank entry rows
    for r in tbl.rows[1:]:
        assert all(c.text.strip() == '' for c in r.cells), "Found non-blank data in Word template!"


def test_word_template_empty_upload_rejected_cleanly(client):
    """Uploading the unedited blank Word template should reject cleanly with 400 (no data rows)."""
    login_as_admin(client)
    res_dl = client.get('/api/master_customers/template/word')
    word_bytes = res_dl.data

    data = {'file': (io.BytesIO(word_bytes), 'TrashTrekyx_Customer_Template.docx')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 400
    res_data = res.get_json()
    assert res_data['success'] is False
    assert 'No data rows found' in res_data['error']


def test_word_template_roundtrip_import(client):
    """Fill downloaded Word template table with customers and import successfully via preview & confirm."""
    login_as_admin(client)
    res_dl = client.get('/api/master_customers/template/word')
    doc = docx.Document(io.BytesIO(res_dl.data))
    tbl = doc.tables[0]

    # Fill row 1 (which is index 1 in tbl.rows)
    r1_cells = tbl.rows[1].cells
    r1_cells[0].text = 'Gamma Retail'
    r1_cells[1].text = '300 Commercial Ave, Ahmedabad'
    r1_cells[2].text = '9876543203'
    r1_cells[3].text = 'https://maps.google.com/?q=23.0500,72.6000'
    r1_cells[4].text = '23.0500'
    r1_cells[5].text = '72.6000'

    # Fill row 2
    r2_cells = tbl.rows[2].cells
    r2_cells[0].text = 'Delta Healthcare'
    r2_cells[1].text = '400 Hospital Road, Ahmedabad'
    r2_cells[2].text = '9876543204'
    r2_cells[3].text = 'https://maps.google.com/?q=23.0600,72.6100'

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    data = {'file': (buf, 'TrashTrekyx_Customer_Template.docx')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['success'] is True
    assert preview['total_detected'] == 2
    assert preview['valid_count'] == 2
    assert preview['ready_to_import_count'] == 2
    assert preview['rows'][0]['name'] == 'Gamma Retail'
    assert preview['rows'][1]['name'] == 'Delta Healthcare'

    # Confirm import
    confirm_res = client.post('/api/master_customers/import_confirm', json={
        'preview_id': preview['preview_id'],
        'destination_template_id': None
    })
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.get_json()
    assert confirm_data['success'] is True
    assert confirm_data['imported'] == 2

    with app.app_context():
        c1 = MasterCustomer.query.filter_by(name='Gamma Retail').first()
        c2 = MasterCustomer.query.filter_by(name='Delta Healthcare').first()
        assert c1 is not None
        assert c2 is not None


# ==============================================================================
# 3. CSV TEMPLATE TESTS
# ==============================================================================

def test_download_csv_template_headers_and_filename(client):
    """Test GET /api/master_customers/template/csv returns 200 with correct filename and headers."""
    login_as_admin(client)
    res = client.get('/api/master_customers/template/csv')
    assert res.status_code == 200
    assert 'attachment' in res.headers.get('Content-Disposition', '')
    assert 'TrashTrekyx_Customer_Template.csv' in res.headers.get('Content-Disposition', '')
    assert 'text/csv' in res.content_type

    text = res.data.decode('utf-8-sig')
    lines = text.strip().splitlines()
    reader = csv.reader(lines)
    rows = list(reader)
    assert rows[0] == EXPECTED_HEADERS


def test_csv_template_has_no_fake_customer_records(client):
    """CSV template must have clean blank data rows and NO fake customer data."""
    login_as_admin(client)
    res = client.get('/api/master_customers/template/csv')
    text = res.data.decode('utf-8-sig')
    lines = text.strip().splitlines()
    reader = csv.reader(lines)
    rows = list(reader)

    # Header + blank lines
    assert len(rows) > 1
    for r in rows[1:]:
        assert all(c.strip() == '' for c in r), f"Found non-blank data in CSV template: {r}"


def test_csv_template_roundtrip_import(client):
    """Fill downloaded CSV template with customers and import successfully via preview & confirm."""
    login_as_admin(client)
    res_dl = client.get('/api/master_customers/template/csv')
    text = res_dl.data.decode('utf-8-sig')
    lines = text.strip().splitlines()

    # Create CSV data with headers and 2 customer rows
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\r\n')
    writer.writerow(EXPECTED_HEADERS)
    writer.writerow(['Epsilon Solar', '500 Solar Way, Ahmedabad', '9876543205', 'https://maps.google.com/?q=23.0700,72.6200', '23.0700', '72.6200'])
    writer.writerow(['Zeta Textiles', '600 Cotton Mill Road, Ahmedabad', '9876543206', 'https://maps.google.com/?q=23.0800,72.6300', '', ''])
    writer.writerow(['', '', '', '', '', '']) # empty row

    csv_bytes = output.getvalue().encode('utf-8-sig')
    data = {'file': (io.BytesIO(csv_bytes), 'TrashTrekyx_Customer_Template.csv')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 200
    preview = res.get_json()
    assert preview['success'] is True
    assert preview['total_detected'] == 2
    assert preview['valid_count'] == 2
    assert preview['ready_to_import_count'] == 2
    assert preview['rows'][0]['name'] == 'Epsilon Solar'
    assert preview['rows'][1]['name'] == 'Zeta Textiles'

    # Confirm import
    confirm_res = client.post('/api/master_customers/import_confirm', json={
        'preview_id': preview['preview_id'],
        'destination_template_id': None
    })
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.get_json()
    assert confirm_data['success'] is True
    assert confirm_data['imported'] == 2

    with app.app_context():
        c1 = MasterCustomer.query.filter_by(name='Epsilon Solar').first()
        c2 = MasterCustomer.query.filter_by(name='Zeta Textiles').first()
        assert c1 is not None
        assert c2 is not None


# ==============================================================================
# 4. AUTHENTICATION & PERMISSIONS ENFORCEMENT
# ==============================================================================

def test_template_downloads_require_authentication(client):
    """Unauthenticated users must be rejected with 401 when accessing template endpoints."""
    res_excel = client.get('/api/master_customers/template/excel')
    assert res_excel.status_code == 401

    res_word = client.get('/api/master_customers/template/word')
    assert res_word.status_code == 401

    res_csv = client.get('/api/master_customers/template/csv')
    assert res_csv.status_code == 401


def test_template_downloads_require_admin_role(client):
    """Driver users must be rejected with 403 when accessing template endpoints."""
    login_as_driver(client)
    res_excel = client.get('/api/master_customers/template/excel')
    assert res_excel.status_code == 403

    res_word = client.get('/api/master_customers/template/word')
    assert res_word.status_code == 403

    res_csv = client.get('/api/master_customers/template/csv')
    assert res_csv.status_code == 403
