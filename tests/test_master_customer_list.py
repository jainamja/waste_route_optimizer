import pytest
import json
from waste_route_optimizer import app, db, User, Customer, SavedTemplate, MasterCustomer
from werkzeug.security import generate_password_hash

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        # Setup test database tables
        db.create_all()
        MasterCustomer.query.delete()
        
        # Ensure an admin user exists
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
            
        # Ensure a driver user exists for auth testing
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

        # Ensure Tuesday Route (5), Thursday Route (8), Wednesday Route (9) exist
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

        t9 = db.session.get(SavedTemplate, 9)
        if not t9:
            t9 = SavedTemplate(id=9, name='Wednesday Route', customers_json='[{"id": 901, "name": "Existing Stop 1", "address": "Addr 1", "truck_id": 1, "stop_number": 1}]', is_assigned_instance=False)
            db.session.add(t9)

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


def test_unauthorized_access(client):
    """Req 15: Verify unauthorized users cannot manage master customers."""
    # 1. Unauthenticated (no session) -> 401
    res = client.get('/api/master_customers')
    assert res.status_code == 401
    
    res = client.post('/api/master_customers', json={'name': 'Hacker', 'address': 'Nowhere'})
    assert res.status_code == 401

    res = client.put('/api/master_customers/1', json={'name': 'Hacker'})
    assert res.status_code == 401

    res = client.delete('/api/master_customers/1')
    assert res.status_code == 401

    res = client.post('/api/templates/5/add_customer', json={'customer_id': 1})
    assert res.status_code == 401

    # 2. Authenticated as DRIVER -> 403 Forbidden
    login_as_driver(client)
    res = client.get('/api/master_customers')
    assert res.status_code == 403

    res = client.post('/api/master_customers', json={'name': 'Hacker', 'address': 'Nowhere'})
    assert res.status_code == 403

    res = client.put('/api/master_customers/1', json={'name': 'Hacker'})
    assert res.status_code == 403

    res = client.delete('/api/master_customers/1')
    assert res.status_code == 403

    res = client.post('/api/templates/5/add_customer', json={'customer_id': 1})
    assert res.status_code == 403


def test_add_master_customer_and_validation(client):
    """Req 1 & 2: Add a new master customer, reject invalid customer data."""
    login_as_admin(client)
    
    # Missing name -> 400
    res = client.post('/api/master_customers', json={'address': '123 Main St'})
    assert res.status_code == 400
    assert 'Customer' in res.get_json()['error']

    # Empty name -> 400
    res = client.post('/api/master_customers', json={'name': '   ', 'address': '123 Main St'})
    assert res.status_code == 400

    # Missing address -> 400
    res = client.post('/api/master_customers', json={'name': 'Green Cafe'})
    assert res.status_code == 400
    assert 'Address' in res.get_json()['error']

    # Invalid latitude (-95) -> 400
    res = client.post('/api/master_customers', json={'name': 'Green Cafe', 'address': '123 Main St', 'phone': '9876543210', 'google_maps_url': 'https://maps.google.com/?q=23.0,72.5', 'lat': -95.0, 'lng': 72.8})
    assert res.status_code == 400

    # Invalid longitude (190) -> 400
    res = client.post('/api/master_customers', json={'name': 'Green Cafe', 'address': '123 Main St', 'phone': '9876543210', 'google_maps_url': 'https://maps.google.com/?q=23.0,72.5', 'lat': 23.0, 'lng': 190.0})
    assert res.status_code == 400

    # Valid customer creation -> 201
    res = client.post('/api/master_customers', json={
        'name': 'Green Cafe',
        'address': '123 Main St, Sector 5',
        'phone': '9876543210',
        'google_maps_url': 'https://maps.google.com/?q=23.0225,72.5714',
        'lat': 23.0225,
        'lng': 72.5714,
        'deliver_bag': True
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data['success'] is True
    cust = data['customer']
    assert cust['name'] == 'Green Cafe'
    assert cust['address'] == '123 Main St, Sector 5'
    assert cust['phone'] == '9876543210'
    assert cust['google_maps_url'] == 'https://maps.google.com/?q=23.0225,72.5714'
    assert cust['lat'] == 23.0225
    assert cust['lng'] == 72.5714
    assert cust['deliver_bag'] is True
    assert cust['customer_status'] == 'ACTIVE'
    assert cust['geocode_quality'] == 'EXACT'
    assert cust['coord_source'] == 'MANUAL'


def test_duplicate_master_customer_prevention(client):
    """Req 3: Prevent duplicate master customer creation."""
    login_as_admin(client)
    
    # First creation
    res1 = client.post('/api/master_customers', json={
        'name': 'Sunset Bakery',
        'address': '456 Ocean Ave',
        'phone': '1122334455',
        'google_maps_url': 'https://maps.google.com/?q=23.0,72.5'
    })
    assert res1.status_code == 201

    # Second creation with identical name & address (case-insensitive) -> 409
    res2 = client.post('/api/master_customers', json={
        'name': 'sunset bakery',
        'address': '456 ocean ave',
        'phone': '9999999999',
        'google_maps_url': 'https://maps.google.com/?q=23.0,72.5'
    })
    assert res2.status_code == 409
    assert 'already exists' in res2.get_json()['error']


def test_list_and_search_master_customers(client):
    """Req 4 & 5: Display all customers, search by name, address, and phone."""
    login_as_admin(client)
    
    # Add customers
    client.post('/api/master_customers', json={'name': 'Alpha Corp', 'address': '789 Business Blvd', 'phone': '55512345', 'google_maps_url': 'https://maps.google.com/?q=23.01,72.51'})
    client.post('/api/master_customers', json={'name': 'Beta Logistics', 'address': '101 Transport Way', 'phone': '55598765', 'google_maps_url': 'https://maps.google.com/?q=23.02,72.52'})
    
    # List all
    res = client.get('/api/master_customers')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['total'] >= 2
    names = [c['name'] for c in data['customers']]
    assert 'Alpha Corp' in names
    assert 'Beta Logistics' in names

    # Search by name
    res_search_name = client.get('/api/master_customers?q=Alpha')
    assert res_search_name.status_code == 200
    search_data = res_search_name.get_json()
    assert any(c['name'] == 'Alpha Corp' for c in search_data['customers'])
    assert not any(c['name'] == 'Beta Logistics' for c in search_data['customers'])

    # Search by address
    res_search_addr = client.get('/api/master_customers?q=Transport')
    assert res_search_addr.status_code == 200
    assert any(c['name'] == 'Beta Logistics' for c in res_search_addr.get_json()['customers'])

    # Search by phone
    res_search_phone = client.get('/api/master_customers?q=55512345')
    assert res_search_phone.status_code == 200
    assert any(c['name'] == 'Alpha Corp' for c in res_search_phone.get_json()['customers'])


def test_edit_customer_information(client):
    """Req 6: Edit customer information."""
    login_as_admin(client)
    
    # Create customer
    res = client.post('/api/master_customers', json={
        'name': 'Original Name',
        'address': 'Original Address',
        'phone': '1111111111',
        'google_maps_url': 'https://maps.google.com/?q=23.0,72.5'
    })
    cust_id = res.get_json()['customer']['id']

    # Update customer details
    put_res = client.put(f'/api/master_customers/{cust_id}', json={
        'name': 'Updated Name Ltd',
        'address': 'Updated Address Suite 200',
        'phone': '2222222222',
        'google_maps_url': 'https://maps.google.com/?q=23.05,72.55',
        'lat': 23.05,
        'lng': 72.55,
        'deliver_bag': True
    })
    assert put_res.status_code == 200
    updated = put_res.get_json()['customer']
    assert updated['name'] == 'Updated Name Ltd'
    assert updated['address'] == 'Updated Address Suite 200'
    assert updated['phone'] == '2222222222'
    assert updated['lat'] == 23.05
    assert updated['lng'] == 72.55
    assert updated['deliver_bag'] is True


def test_add_customer_to_multiple_templates_and_duplicate_prevention(client):
    """
    Req 7, 8, 9, 10, 11:
    - Add customer to Tuesday Route (#5)
    - Add the same customer to Thursday Route (#8)
    - Prevent duplicate addition to the same template
    - Verify other templates (Wednesday Route #9) remain unchanged
    - Verify assigned routes remain unchanged until deployment
    """
    login_as_admin(client)
    
    # Create a single master customer record
    res = client.post('/api/master_customers', json={
        'name': 'Cafe Coffee Day',
        'address': 'Ring Road, Sector 3',
        'phone': '9898989898',
        'google_maps_url': 'https://maps.google.com/?q=23.04,72.58',
        'lat': 23.04,
        'lng': 72.58
    })
    assert res.status_code == 201
    cust_id = res.get_json()['customer']['id']

    # 1. Add to Tuesday Route (ID 5)
    t5_res = client.post('/api/templates/5/add_customer', json={'customer_id': cust_id})
    assert t5_res.status_code == 200
    assert 'Tuesday Route' in t5_res.get_json()['message']

    # Verify Tuesday Route customer_json contains this customer
    with app.app_context():
        t5 = db.session.get(SavedTemplate, 5)
        t5_custs = json.loads(t5.customers_json or '[]')
        assert any(c.get('master_customer_id') == cust_id or c.get('id') == cust_id for c in t5_custs)
        assert any(c.get('name') == 'Cafe Coffee Day' for c in t5_custs)

    # 2. Duplicate addition to Tuesday Route (ID 5) must be rejected with 409
    t5_dup_res = client.post('/api/templates/5/add_customer', json={'customer_id': cust_id})
    assert t5_dup_res.status_code == 409
    assert 'Already added to this template' in t5_dup_res.get_json()['message']

    # 3. Add same customer to Thursday Route (ID 8) -> Must succeed!
    t8_res = client.post('/api/templates/8/add_customer', json={'customer_id': cust_id})
    assert t8_res.status_code == 200
    assert 'Thursday Route' in t8_res.get_json()['message']

    with app.app_context():
        t8 = db.session.get(SavedTemplate, 8)
        t8_custs = json.loads(t8.customers_json or '[]')
        assert any(c.get('master_customer_id') == cust_id or c.get('id') == cust_id for c in t8_custs)
        assert any(c.get('name') == 'Cafe Coffee Day' for c in t8_custs)

    # 4. Verify Wednesday Route (ID 9) was NOT touched
    with app.app_context():
        t9 = db.session.get(SavedTemplate, 9)
        t9_custs = json.loads(t9.customers_json or '[]')
        assert not any(c.get('name') == 'Cafe Coffee Day' for c in t9_custs)
        # Ensure Wednesday route stops remain unchanged
        assert len(t9_custs) >= 1

    # 5. Verify Master Customer database still has only ONE single master customer record
    with app.app_context():
        count = MasterCustomer.query.filter_by(name='Cafe Coffee Day').count()
        assert count == 1

    # 6. Verify GET /api/master_customers reflects membership in both templates
    list_res = client.get('/api/master_customers?q=Cafe Coffee Day')
    assert list_res.status_code == 200
    item = list_res.get_json()['customers'][0]
    assert 'Tuesday Route' in item['templates']
    assert 'Thursday Route' in item['templates']


def test_archive_behavior_and_safe_delete(client):
    """Req 16: Verify archive behavior for customers referenced by routes or templates."""
    login_as_admin(client)
    
    # Create master customer
    res = client.post('/api/master_customers', json={
        'name': 'Heritage Hotel',
        'address': '55 Heritage St',
        'phone': '7778889999',
        'google_maps_url': 'https://maps.google.com/?q=23.05,72.55'
    })
    cust_id = res.get_json()['customer']['id']

    # Add to Tuesday Route
    client.post('/api/templates/5/add_customer', json={'customer_id': cust_id})

    # Delete (archive) customer
    del_res = client.delete(f'/api/master_customers/{cust_id}')
    assert del_res.status_code == 200
    assert 'archived successfully' in del_res.get_json()['message']

    # Record is not destroyed; marked ARCHIVED
    with app.app_context():
        cust = db.session.get(MasterCustomer, cust_id)
        assert cust is not None
        assert cust.customer_status == 'ARCHIVED'

    # Excluded from active master list by default
    active_res = client.get('/api/master_customers')
    active_names = [c['name'] for c in active_res.get_json()['customers']]
    assert 'Heritage Hotel' not in active_names

    # Included when querying archived
    archived_res = client.get('/api/master_customers?status=ARCHIVED')
    archived_names = [c['name'] for c in archived_res.get_json()['customers']]
    assert 'Heritage Hotel' in archived_names


def test_assigned_routes_and_driver_progress_remain_unchanged(client):
    """
    Req 11, 14:
    - Adding customer to Saved Template does NOT change assigned routes.
    - Driver progress and completions remain completely intact.
    """
    login_as_admin(client)

    with app.app_context():
        # Setup an active assigned route on Truck 1
        driver = User.query.filter_by(role='DRIVER').first()
        driver.truck_id = 1
        driver.assigned_template_id = 5
        
        # Add an active customer on truck 1
        Customer.query.filter_by(truck_id=1).delete()
        c_active = Customer(
            id=777,
            name='Active Stop 1',
            truck_id=1,
            stop_number=1,
            status='COMPLETED',
            confirmation='CONFIRMED',
            customer_status='ACTIVE'
        )
        db.session.add(c_active)
        db.session.commit()

    # Create new master customer and add to Tuesday Route (5)
    res = client.post('/api/master_customers', json={
        'name': 'New Unassigned Client',
        'address': '99 New Ave',
        'phone': '9123456789',
        'google_maps_url': 'https://maps.google.com/?q=23.06,72.56'
    })
    cust_id = res.get_json()['customer']['id']

    # Add to Tuesday Route template
    add_res = client.post('/api/templates/5/add_customer', json={'customer_id': cust_id})
    assert add_res.status_code == 200

    # Verify active customer on Truck 1 is completely unchanged
    with app.app_context():
        active_stop = db.session.get(Customer, 777)
        assert active_stop is not None
        assert active_stop.status == 'COMPLETED'
        assert active_stop.confirmation == 'CONFIRMED'
        assert active_stop.stop_number == 1

        # Verify the new master customer does NOT appear in active Customer table
        new_active = Customer.query.filter_by(name='New Unassigned Client').first()
        assert new_active is None, "Master customer must NOT be automatically deployed to active Customer table!"


def test_optimizer_and_vrp_preservation():
    """Req 12: Route optimization algorithms remain functional."""
    from aco_vrp import ACO_VRP
    depot_start = (23.0225, 72.5714)
    depot_end = (23.2770, 72.4335)
    customers = [
        {'id': 1, 'lat': 23.03, 'lng': 72.58},
        {'id': 2, 'lat': 23.04, 'lng': 72.59}
    ]
    aco = ACO_VRP(depot_start, depot_end, customers, num_trucks=1)
    routes, times, distances = aco.run()
    assert len(routes) == 1
    assert set(routes[0]) == {1, 2}


def test_master_acceptance_condition(client):
    """
    FINAL ACCEPTANCE CONDITION:
    The admin must be able to create one customer in the Master Customer List
    and add that same customer directly to multiple existing Saved Templates
    without creating duplicate customer records or changing existing assigned routes.
    """
    login_as_admin(client)

    # 1. Admin creates ONE customer in the Master Customer List
    create_res = client.post('/api/master_customers', json={
        'name': 'Grand Plaza Hotel',
        'address': '500 Grand Way',
        'phone': '1234567890',
        'google_maps_url': 'https://maps.google.com/?q=23.05,72.56',
        'lat': 23.05,
        'lng': 72.56,
        'deliver_bag': True
    })
    assert create_res.status_code == 201
    cust_id = create_res.get_json()['customer']['id']

    # 2. Add customer to Tuesday Route (#5)
    res_t5 = client.post('/api/templates/5/add_customer', json={'customer_id': cust_id})
    assert res_t5.status_code == 200

    # 3. Add same customer to Thursday Route (#8)
    res_t8 = client.post('/api/templates/8/add_customer', json={'customer_id': cust_id})
    assert res_t8.status_code == 200

    # 4. Attempting to add duplicate to Tuesday Route is rejected
    res_t5_dup = client.post('/api/templates/5/add_customer', json={'customer_id': cust_id})
    assert res_t5_dup.status_code == 409
    assert 'Already added to this template' in res_t5_dup.get_json()['message']

    # 5. Master database has exactly ONE record for this customer
    with app.app_context():
        records = MasterCustomer.query.filter_by(name='Grand Plaza Hotel').all()
        assert len(records) == 1
        assert records[0].id == cust_id

    # 6. Both templates independently retain the customer
    with app.app_context():
        t5 = db.session.get(SavedTemplate, 5)
        t5_custs = json.loads(t5.customers_json or '[]')
        assert any(c.get('master_customer_id') == cust_id for c in t5_custs)

        t8 = db.session.get(SavedTemplate, 8)
        t8_custs = json.loads(t8.customers_json or '[]')
        assert any(c.get('master_customer_id') == cust_id for c in t8_custs)


def test_admin_dashboard_ui_elements(client):
    """Req 1: Verify Master Customer List Quick Action card and section on Admin Dashboard."""
    login_as_admin(client)
    res = client.get('/admin')
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # 1. Quick Action card
    assert 'Master Customer List' in html
    assert 'Manage all registered customers, add new customers, and add them directly to your saved route templates.' in html

    # 2. Clearly visible Master Customer List section
    assert 'id="master-customer-section"' in html
    assert 'id="master-customer-list"' in html
    assert 'id="master-cust-search"' in html
    assert 'Add Customer' in html

    # 3. Modals
    assert 'id="add-customer-modal"' in html
    assert 'id="edit-customer-modal"' in html
    assert 'id="add-to-template-modal"' in html
    assert 'id="destination-template-select"' in html

    # 4. JavaScript hooks
    assert 'loadMasterCustomers()' in html
    assert 'openAddToTemplateModal' in html


def test_add_new_customer_modal_no_deliver_bag(client):
    """Verify Deliver Waste Collection Bag checkbox is removed from Add New Customer modal and Google Maps fields are present."""
    login_as_admin(client)
    res = client.get('/admin')
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Add Customer Modal has all required fields
    assert 'id="new-cust-name"' in html
    assert 'id="new-cust-address"' in html
    assert 'id="new-cust-phone"' in html
    assert 'id="new-cust-maps-url"' in html
    assert 'id="new-cust-lat"' in html
    assert 'id="new-cust-lng"' in html
    assert 'id="btn-save-customer"' in html

    # Deliver Waste Collection Bag is removed from Add Customer Modal
    assert 'id="new-cust-deliver-bag"' not in html
    assert 'for="new-cust-deliver-bag"' not in html

    # Edit Customer Modal has Google Maps URL
    assert 'id="edit-cust-maps-url"' in html



