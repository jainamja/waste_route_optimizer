import os
import sys
import json
import pytest
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from werkzeug.security import generate_password_hash

from waste_route_optimizer import (
    app, db, User, Customer, SavedTemplate, MasterCustomer,
    migrate_saved_template_customers_to_master
)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(username='admin_tab_tester').first()
        if not admin:
            admin = User(
                username='admin_tab_tester',
                password_hash=generate_password_hash('admintabpass123'),
                role='ADMIN',
                name='Admin Tab Tester',
                is_superadmin=True
            )
            db.session.add(admin)
            db.session.commit()

        restricted_driver = User.query.filter_by(username='restricted_driver_tab').first()
        if not restricted_driver:
            restricted_driver = User(
                username='restricted_driver_tab',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Restricted Driver Tab'
            )
            db.session.add(restricted_driver)
            db.session.commit()

        admin_id = admin.id
        admin_username = admin.username

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['username'] = admin_username
            sess['role'] = 'ADMIN'
            sess['is_superadmin'] = True
        yield c


def test_dedicated_master_customer_routes_return_200(client):
    """Verify that dedicated routes for Master Customer List render successfully."""
    for path in ['/master-customers', '/admin/customers', '/admin?tab=customers']:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 for {path}, got {res.status_code}"
        html = res.data.decode('utf-8')
        assert 'SERVER_INITIAL_TAB = "customers"' in html or "SERVER_INITIAL_TAB = 'customers'" in html
        assert 'id="tab-btn-customers"' in html
        assert 'id="pane-customers"' in html


def test_dedicated_saved_templates_routes_return_200(client):
    """Verify that dedicated routes for Saved Templates render successfully."""
    for path in ['/saved-templates', '/admin/templates', '/admin?tab=templates']:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 for {path}, got {res.status_code}"
        html = res.data.decode('utf-8')
        assert 'SERVER_INITIAL_TAB = "templates"' in html or "SERVER_INITIAL_TAB = 'templates'" in html
        assert 'id="tab-btn-templates"' in html
        assert 'id="pane-templates"' in html


def test_dom_separation_master_customer_and_saved_templates(client):
    """Verify that Master Customer List and Saved Templates are in separate, independent panes."""
    res = client.get('/admin')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    soup = BeautifulSoup(html, 'html.parser')

    pane_customers = soup.find('div', id='pane-customers')
    pane_templates = soup.find('div', id='pane-templates')
    pane_overview = soup.find('div', id='pane-overview')

    assert pane_customers is not None, "Pane customers must exist"
    assert pane_templates is not None, "Pane templates must exist"
    assert pane_overview is not None, "Pane overview must exist"

    # Verify they are siblings or completely separate, neither nested within the other
    assert pane_templates not in pane_customers.descendants, "Saved Templates must not be inside Master Customer pane"
    assert pane_customers not in pane_templates.descendants, "Master Customer List must not be inside Saved Templates pane"

    # Master Customer section must be in pane_customers
    master_section = pane_customers.find(id='master-customer-section')
    assert master_section is not None, "#master-customer-section must be inside #pane-customers"

    # Saved Templates section must be in pane_templates
    templates_section = pane_templates.find(id='saved-templates-section')
    assert templates_section is not None, "#saved-templates-section must be inside #pane-templates"

    # Navigation buttons exist
    assert soup.find('button', id='tab-btn-customers') is not None
    assert soup.find('button', id='tab-btn-templates') is not None
    assert soup.find('button', id='tab-btn-overview') is not None


def test_add_customer_to_template_preserves_master_customer(client):
    """
    Verify that adding a customer to a Saved Template does not delete
    or remove them from the Master Customer List.
    """
    with app.app_context():
        # Ensure fresh unique customer in MasterCustomer
        mc = MasterCustomer.query.filter_by(phone='+15559870001').first()
        if not mc:
            mc = MasterCustomer(
                name='Preserved Tab Test Customer',
                address='456 Preserved Way, Sector 9',
                phone='+15559870001',
                google_maps_url='https://maps.google.com/?q=456+Preserved+Way',
                location_url='https://maps.google.com/?q=456+Preserved+Way',
                lat=28.6139,
                lng=77.2090,
                deliver_bag=True,
                customer_status='ACTIVE'
            )
            db.session.add(mc)
            db.session.commit()
        else:
            mc.customer_status = 'ACTIVE'
            db.session.commit()
        master_id = mc.id

        # Ensure a test SavedTemplate exists
        tmpl = SavedTemplate.query.filter_by(name='Tab Preservation Template').first()
        if not tmpl:
            tmpl = SavedTemplate(
                name='Tab Preservation Template',
                metadata_json='{}',
                customers_json='[]'
            )
            db.session.add(tmpl)
            db.session.commit()
        else:
            tmpl.customers_json = '[]'
            db.session.commit()
        tmpl_id = tmpl.id

    # Post add_customer to template
    payload = {
        'customer_id': master_id
    }
    res = client.post(f'/api/templates/{tmpl_id}/add_customer',
                      data=json.dumps(payload),
                      content_type='application/json')
    assert res.status_code in [200, 201]

    # Verify customer still exists in MasterCustomer and is NOT archived
    with app.app_context():
        master_cust = db.session.get(MasterCustomer, master_id)
        assert master_cust is not None, "Customer must still exist in MasterCustomer"
        assert master_cust.customer_status == 'ACTIVE', "Customer must remain active in MasterCustomer"
        assert master_cust.name == 'Preserved Tab Test Customer'

        # Also verify customer is in template's customers_json
        saved_tmpl = db.session.get(SavedTemplate, tmpl_id)
        cust_list = json.loads(saved_tmpl.customers_json or '[]')
        matched = [c for c in cust_list if c.get('phone') == '+15559870001' or c.get('master_customer_id') == master_id]
        assert len(matched) >= 1, "Customer should be attached to the SavedTemplate"



def test_unauthenticated_access_is_blocked():
    """Verify that unauthenticated users cannot access dedicated admin tabs."""
    with app.test_client() as anon_client:
        for path in ['/master-customers', '/admin/customers', '/saved-templates', '/admin/templates']:
            res = anon_client.get(path)
            # Should redirect to login (302) or return 401/403
            assert res.status_code in [302, 401, 403], f"Unexpected status {res.status_code} for anonymous on {path}"


def test_restricted_driver_access_is_blocked():
    """Verify that a driver without admin role cannot access dedicated admin tabs."""
    with app.app_context():
        driver = User.query.filter_by(username='restricted_driver_tab').first()
        driver_id = driver.id
        driver_username = driver.username

    with app.test_client() as driver_client:
        with driver_client.session_transaction() as sess:
            sess['user_id'] = driver_id
            sess['username'] = driver_username
            sess['role'] = 'DRIVER'
            sess['is_superadmin'] = False

        for path in ['/master-customers', '/admin/customers', '/saved-templates', '/admin/templates']:
            res = driver_client.get(path)
            # Should be blocked with 403 or redirect
            assert res.status_code in [302, 403], f"Driver should not access {path}"


def test_javascript_tab_switching_logic_present(client):
    """Verify JavaScript tab switching functions and elements are present."""
    res = client.get('/admin')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert 'function switchAdminTab(tabName)' in html
    assert 'currentActiveTab = tabName' in html
    assert 'history.replaceState' in html
    assert 'loadMasterCustomers()' in html
    assert 'loadTemplates()' in html
