import pytest
import json
from waste_route_optimizer import (
    app, db, User, UserPermission, AdminAuditLog, SavedTemplate, MasterCustomer,
    PERMISSION_MODULES, ALL_PERMISSION_KEYS
)
from werkzeug.security import generate_password_hash

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        # Clean up permissions, audit logs, customers, and non-admin test users for clean test runs
        UserPermission.query.delete()
        AdminAuditLog.query.delete()
        MasterCustomer.query.delete()
        User.query.filter(User.username != 'admin').delete()

        # Ensure primary superadmin exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                role='ADMIN',
                name='Primary Admin',
                email='admin@trashtrekyx.com',
                is_active=True,
                is_superadmin=True,
                auth_version=1
            )
            db.session.add(admin)
        else:
            admin.is_superadmin = True
            admin.is_active = True
            admin.auth_version = 1

        # Ensure test driver exists
        driver = User.query.filter_by(username='driver_test').first()
        if not driver:
            driver = User(
                username='driver_test',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Driver Test',
                is_active=True,
                truck_id=1,
                auth_version=1
            )
            db.session.add(driver)

        # Ensure a test template exists
        t = db.session.get(SavedTemplate, 5)
        if not t:
            t = SavedTemplate(id=5, name='Tuesday Route', customers_json='[{"id": 101, "name": "Stop 1", "address": "Addr 1", "truck_id": 1, "stop_number": 1}]', is_assigned_instance=False)
            db.session.add(t)

        db.session.commit()

    with app.test_client() as client:
        yield client

def login_user(client, user):
    """Helper to simulate logging in as a specific user."""
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['auth_version'] = getattr(user, 'auth_version', 1)

def get_admin_user():
    return User.query.filter_by(username='admin').first()

def test_primary_admin_retains_superadmin_and_full_access(client):
    """Test 1: Primary administrator has superadmin rights and full system access."""
    with app.app_context():
        admin = get_admin_user()
        assert admin.is_superadmin is True
        assert admin.is_active is True

    login_user(client, admin)

    # Superadmin can access metadata
    res = client.get('/api/admin/permissions_meta')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert len(data['modules']) == 8

    # Superadmin can view user list
    res = client.get('/api/admin/users')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert any(u['username'] == 'admin' for u in data['users'])

    # Superadmin can view customers
    res = client.get('/api/master_customers')
    assert res.status_code == 200

    # Superadmin can access /api/auth/me
    res = client.get('/api/auth/me')
    assert res.status_code == 200
    me = res.get_json()['user']
    assert me['is_superadmin'] is True
    assert len(me['permissions']) == len(ALL_PERMISSION_KEYS)


def test_create_admin_user_validation(client):
    """Test 2: Validation on user creation (password strength, uniqueness, required fields)."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    # Missing fields
    res = client.post('/api/admin/users', json={'username': 'test1'})
    assert res.status_code == 400

    # Password too short (< 8 chars)
    res = client.post('/api/admin/users', json={
        'name': 'Short PW',
        'username': 'shortpw',
        'email': 'short@example.com',
        'password': 'pass1'
    })
    assert res.status_code == 400
    assert '8 characters' in res.get_json()['error']

    # Password lacks letters or numbers
    res = client.post('/api/admin/users', json={
        'name': 'No Digits',
        'username': 'nodigits',
        'email': 'nodigits@example.com',
        'password': 'passwordonly'
    })
    assert res.status_code == 400

    # Valid creation
    res = client.post('/api/admin/users', json={
        'name': 'Valid User',
        'username': 'validuser',
        'email': 'validuser@example.com',
        'password': 'ValidPass123',
        'permissions': ['customers.view', 'customers.create']
    })
    assert res.status_code == 201
    created_id = res.get_json()['user']['id']

    # Duplicate username
    res = client.post('/api/admin/users', json={
        'name': 'Duplicate User',
        'username': 'validuser',
        'email': 'another@example.com',
        'password': 'ValidPass123'
    })
    assert res.status_code == 409
    assert 'Username' in res.get_json()['error']

    # Duplicate email
    res = client.post('/api/admin/users', json={
        'name': 'Duplicate Email',
        'username': 'anotheruser',
        'email': 'validuser@example.com',
        'password': 'ValidPass123'
    })
    assert res.status_code == 409
    assert 'Email' in res.get_json()['error']


def test_view_only_user_permissions(client):
    """Test 3: View-only user can view but write actions return 403 Forbidden."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    # Create view-only user
    res = client.post('/api/admin/users', json={
        'name': 'View Only User',
        'username': 'viewonly',
        'email': 'viewonly@trashtrekyx.com',
        'password': 'ViewOnlyPass123',
        'permissions': ['routes.view']
    })
    assert res.status_code == 201

    with app.app_context():
        viewer = User.query.filter_by(username='viewonly').first()

    # Log in as viewer
    login_user(client, viewer)

    # Allowed: view assigned routes
    res = client.get('/api/assigned_routes')
    assert res.status_code == 200

    # Forbidden: assign driver
    res = client.post('/api/assign_driver', json={'route_id': 1, 'driver_id': 1})
    assert res.status_code == 403

    # Forbidden: remove stop
    res = client.post('/api/remove_stop', json={'route_id': 1, 'stop_id': 101})
    assert res.status_code == 403

    # Forbidden: create customer
    res = client.post('/api/master_customers', json={'name': 'Customer', 'address': 'Addr'})
    assert res.status_code == 403

    # Forbidden: view user management
    res = client.get('/api/admin/users')
    assert res.status_code == 403


def test_customer_manager_permissions(client):
    """Test 4: Customer-manager can manage customers but cannot touch routes or drivers."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    # Create customer manager
    res = client.post('/api/admin/users', json={
        'name': 'Cust Manager',
        'username': 'custmgr',
        'email': 'custmgr@trashtrekyx.com',
        'password': 'CustPass123',
        'permissions': ['customers.view', 'customers.create', 'customers.edit', 'customers.archive']
    })
    assert res.status_code == 201

    with app.app_context():
        mgr = User.query.filter_by(username='custmgr').first()

    login_user(client, mgr)

    # Allowed: create customer
    res = client.post('/api/master_customers', json={'name': 'Green Cafe', 'address': 'MG Road 1'})
    assert res.status_code == 201
    cust_id = res.get_json()['customer']['id']

    # Allowed: edit customer
    res = client.put(f'/api/master_customers/{cust_id}', json={'name': 'Green Cafe Updated'})
    assert res.status_code == 200

    # Allowed: archive customer
    res = client.delete(f'/api/master_customers/{cust_id}')
    assert res.status_code == 200

    # Forbidden: deploy template
    res = client.post('/api/deploy_template/5?mode=deploy')
    assert res.status_code == 403

    # Forbidden: create driver
    res = client.post('/api/admin_create_driver', json={'name': 'Driver', 'phone': '9999999999', 'password': 'pass'})
    assert res.status_code == 403


def test_route_manager_permissions(client):
    """Test 5: Route manager can manage routes but cannot manage users or delete drivers."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    res = client.post('/api/admin/users', json={
        'name': 'Route Manager',
        'username': 'routemgr',
        'email': 'routemgr@trashtrekyx.com',
        'password': 'RoutePass123',
        'permissions': ['routes.view', 'routes.edit', 'routes.assign_driver']
    })
    assert res.status_code == 201

    with app.app_context():
        rm = User.query.filter_by(username='routemgr').first()

    login_user(client, rm)

    # Allowed: view routes
    res = client.get('/api/assigned_routes')
    assert res.status_code == 200

    # Forbidden: User management
    res = client.get('/api/admin/users')
    assert res.status_code == 403

    # Forbidden: Delete driver
    res = client.delete('/api/admin_delete_driver/1')
    assert res.status_code == 403


def test_grant_and_update_permissions_api(client):
    """Test 6: Admin updates permissions via API and changes take effect immediately."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    # Create user with no initial permissions
    res = client.post('/api/admin/users', json={
        'name': 'Perm User',
        'username': 'permuser',
        'email': 'permuser@trashtrekyx.com',
        'password': 'PermPass123',
        'permissions': []
    })
    user_id = res.get_json()['user']['id']

    with app.app_context():
        u = db.session.get(User, user_id)

    # Check user cannot view customers
    login_user(client, u)
    res = client.get('/api/master_customers')
    assert res.status_code == 403

    # Admin grants customers.view
    login_user(client, admin)
    res = client.put(f'/api/admin/users/{user_id}/permissions', json={
        'permissions': ['customers.view']
    })
    assert res.status_code == 200

    # User re-logs in (or refreshes session with new auth_version)
    with app.app_context():
        u = db.session.get(User, user_id)
    login_user(client, u)
    res = client.get('/api/master_customers')
    assert res.status_code == 200


def test_revoke_permissions_api(client):
    """Test 7: Admin revokes specific permissions and actions are blocked."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    res = client.post('/api/admin/users', json={
        'name': 'Revoke User',
        'username': 'revokeuser',
        'email': 'revokeuser@trashtrekyx.com',
        'password': 'RevokePass123',
        'permissions': ['customers.view', 'customers.create']
    })
    user_id = res.get_json()['user']['id']

    # Admin strips customers.create
    res = client.put(f'/api/admin/users/{user_id}/permissions', json={
        'permissions': ['customers.view']
    })
    assert res.status_code == 200

    with app.app_context():
        u = db.session.get(User, user_id)
    login_user(client, u)

    # View is OK
    res = client.get('/api/master_customers')
    assert res.status_code == 200

    # Create is Forbidden
    res = client.post('/api/master_customers', json={'name': 'Disallowed', 'address': 'Addr'})
    assert res.status_code == 403


def test_deactivate_and_reactivate_user(client):
    """Test 8: Deactivated user cannot log in and active sessions lose access immediately."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    res = client.post('/api/admin/users', json={
        'name': 'Deact User',
        'username': 'deactuser',
        'email': 'deactuser@trashtrekyx.com',
        'password': 'DeactPass123',
        'permissions': ['customers.view']
    })
    user_id = res.get_json()['user']['id']

    # User logs in via /login
    res = client.post('/login', data={'username': 'deactuser', 'password': 'DeactPass123'})
    assert res.status_code == 302  # redirects to admin or routes

    # User can access /api/master_customers
    res = client.get('/api/master_customers')
    assert res.status_code == 200

    # Admin deactivates user
    login_user(client, admin)
    res = client.put(f'/api/admin/users/{user_id}/status', json={'is_active': False})
    assert res.status_code == 200

    # User's existing session is now immediately rejected
    # In client session, user_id is still set, but auth_version was bumped and user is inactive
    login_user(client, User(id=user_id, auth_version=1))  # old auth_version
    res = client.get('/api/master_customers')
    assert res.status_code in [401, 403]

    # User tries to log in again with credentials
    res = client.post('/login', data={'username': 'deactuser', 'password': 'DeactPass123'})
    assert res.status_code == 200
    assert b'deactivated' in res.data or b'Invalid' in res.data


def test_session_revocation_instant_invalidation(client):
    """Test 9: Calling /revoke invalidates active session immediately via auth_version bump."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    res = client.post('/api/admin/users', json={
        'name': 'Revoke Session User',
        'username': 'sessionuser',
        'email': 'sessionuser@trashtrekyx.com',
        'password': 'SessionPass123',
        'permissions': ['customers.view']
    })
    user_id = res.get_json()['user']['id']

    with app.app_context():
        u = db.session.get(User, user_id)

    # User session with auth_version = 1
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['auth_version'] = 1

    res = client.get('/api/master_customers')
    assert res.status_code == 200

    # Admin revokes user session
    login_user(client, admin)
    res = client.post(f'/api/admin/users/{user_id}/revoke')
    assert res.status_code == 200

    # User tries next request with old session
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['auth_version'] = 1

    res = client.get('/api/master_customers')
    assert res.status_code == 401


def test_direct_unauthorized_api_requests(client):
    """Test 10: Direct unauthorized HTTP requests without permission return 403."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    # User with zero permissions
    res = client.post('/api/admin/users', json={
        'name': 'Zero Perms',
        'username': 'zeroperms',
        'email': 'zeroperms@trashtrekyx.com',
        'password': 'ZeroPass123',
        'permissions': []
    })
    with app.app_context():
        zero = User.query.filter_by(username='zeroperms').first()
    login_user(client, zero)

    # Test variety of protected endpoints
    endpoints = [
        ('POST', '/api/admin_create_driver', {'name': 'X', 'phone': '1', 'password': '1'}),
        ('POST', '/api/admin_set_driver_truck', {'driver_id': 1, 'truck_id': 1}),
        ('DELETE', '/api/admin_delete_driver/1', None),
        ('POST', '/api/deploy_template/5?mode=deploy', None),
        ('DELETE', '/api/delete_template/5', None),
        ('POST', '/api/save_template', {'name': 'T', 'customers': []}),
        ('GET', '/api/admin/users', None),
        ('POST', '/api/admin/users', {'name': 'Y'}),
        ('GET', '/api/admin/audit_logs', None),
    ]

    for method, path, body in endpoints:
        if method == 'POST':
            r = client.post(path, json=body or {})
        elif method == 'DELETE':
            r = client.delete(path)
        else:
            r = client.get(path)
        assert r.status_code == 403, f"Expected 403 for {method} {path}, got {r.status_code}"


def test_unauthorized_file_import(client):
    """Test 11: File import endpoints require specific import permissions."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    # User with only customers.view and customers.create, but NO customers.import_excel
    res = client.post('/api/admin/users', json={
        'name': 'No Import User',
        'username': 'noimport',
        'email': 'noimport@trashtrekyx.com',
        'password': 'NoImportPass123',
        'permissions': ['customers.view', 'customers.create']
    })
    with app.app_context():
        u = User.query.filter_by(username='noimport').first()
    login_user(client, u)

    import io
    fake_excel = io.BytesIO(b'Fake excel bytes')
    data = {'file': (fake_excel, 'customers.xlsx')}
    res = client.post('/api/master_customers/import_preview', data=data, content_type='multipart/form-data')
    assert res.status_code == 403


def test_privilege_escalation_prevention(client):
    """Test 12: Ordinary admin cannot create superadmins or grant unowned permissions."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    # Create admin with users.view and users.create, but not superadmin
    res = client.post('/api/admin/users', json={
        'name': 'Sub Admin',
        'username': 'subadmin',
        'email': 'subadmin@trashtrekyx.com',
        'password': 'SubAdminPass123',
        'permissions': ['users.view', 'users.create']
    })
    with app.app_context():
        sub = User.query.filter_by(username='subadmin').first()
    login_user(client, sub)

    # Attempt to create a superadmin user -> 403
    res = client.post('/api/admin/users', json={
        'name': 'Escalated Super',
        'username': 'escalated',
        'email': 'escalated@trashtrekyx.com',
        'password': 'EscalatedPass123',
        'is_superadmin': True
    })
    assert res.status_code == 403

    # Attempt to grant permission subadmin doesn't possess (e.g. routes.delete) -> 403
    res = client.post('/api/admin/users', json={
        'name': 'Escalated Perms',
        'username': 'escalated_p',
        'email': 'escalated_p@trashtrekyx.com',
        'password': 'EscalatedPass123',
        'permissions': ['routes.delete']
    })
    assert res.status_code == 403


def test_self_promotion_prevention(client):
    """Test 13: Ordinary admin cannot edit their own permissions."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    res = client.post('/api/admin/users', json={
        'name': 'Self Admin',
        'username': 'selfadmin',
        'email': 'selfadmin@trashtrekyx.com',
        'password': 'SelfAdminPass123',
        'permissions': ['users.view', 'users.change_permissions']
    })
    with app.app_context():
        self_admin = User.query.filter_by(username='selfadmin').first()
    login_user(client, self_admin)

    # Attempt to grant self all permissions
    res = client.put(f'/api/admin/users/{self_admin.id}/permissions', json={
        'permissions': list(ALL_PERMISSION_KEYS)
    })
    assert res.status_code == 403


def test_primary_admin_and_last_superadmin_protection(client):
    """Test 14: Primary admin and last superadmin cannot be deleted, deactivated, or demoted."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    # Attempt to deactivate admin
    res = client.put(f'/api/admin/users/{admin.id}/status', json={'is_active': False})
    assert res.status_code == 403

    # Attempt to strip superadmin from admin
    res = client.put(f'/api/admin/users/{admin.id}/permissions', json={'permissions': ['customers.view']})
    assert res.status_code == 403


def test_driver_authentication_and_mobile_isolation(client):
    """Test 15: Driver authentication remains unaffected and drivers cannot access admin endpoints."""
    with app.app_context():
        driver = User.query.filter_by(username='driver_test').first()

    # Driver login endpoint works
    res = client.post('/api/driver_login', json={
        'username': 'driver_test',
        'password': 'driverpass123'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data.get('role') == 'DRIVER'
    assert 'token' in data

    # Driver cannot access admin user management
    login_user(client, driver)
    res = client.get('/api/admin/users')
    assert res.status_code == 403


def test_admin_audit_logging(client):
    """Test 16: Admin operations generate audit logs in AdminAuditLog table."""
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    res = client.post('/api/admin/users', json={
        'name': 'Audit User',
        'username': 'audituser',
        'email': 'audituser@trashtrekyx.com',
        'password': 'AuditPass123',
        'permissions': ['customers.view']
    })
    assert res.status_code == 201
    user_id = res.get_json()['user']['id']

    res = client.get('/api/admin/audit_logs')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert len(data['logs']) >= 1
    actions = [log['action'] for log in data['logs']]
    assert 'USER_CREATED' in actions


def test_complete_acceptance_workflow_the_rahul_test(client):
    """
    Test 17: Section 13 Master Acceptance Test - 'The Rahul Test'
    1. Primary Admin creates user 'rahul' with ONLY customers.view, customers.create, customers.edit.
    2. Rahul logs in.
    3. Rahul views customer list: 200 OK.
    4. Rahul creates new customer: 201 Created.
    5. Rahul edits customer: 200 OK.
    6. Rahul attempts to deploy a Saved Template: 403 Forbidden.
    7. Rahul attempts to create a driver: 403 Forbidden.
    8. Rahul attempts to access User Management: 403 Forbidden.
    9. Admin adds templates.view and templates.deploy to Rahul's permissions.
    10. Rahul re-attempts deploy: 200 OK.
    11. Admin deactivates Rahul.
    12. Rahul's active session is rejected immediately on next request.
    13. Rahul tries to log in again: rejected.
    """
    # 1. Primary Admin creates 'rahul'
    with app.app_context():
        admin = get_admin_user()
    login_user(client, admin)

    res = client.post('/api/admin/users', json={
        'name': 'Rahul Sharma',
        'username': 'rahul',
        'email': 'rahul@trashtrekyx.com',
        'password': 'RahulPassword123',
        'is_active': True,
        'permissions': ['customers.view', 'customers.create', 'customers.edit']
    })
    assert res.status_code == 201
    rahul_id = res.get_json()['user']['id']

    # 2. Rahul logs in via /login
    client.get('/logout')
    res = client.post('/login', data={'username': 'rahul', 'password': 'RahulPassword123'})
    assert res.status_code == 302

    # 3. Rahul views customer list -> 200 OK
    res = client.get('/api/master_customers')
    assert res.status_code == 200

    # 4. Rahul creates new customer -> 201 Created
    res = client.post('/api/master_customers', json={
        'name': 'Rahul Fresh Market',
        'address': 'Plot 42, GIDC Estate',
        'phone': '9876543210'
    })
    assert res.status_code == 201
    created_cust_id = res.get_json()['customer']['id']

    # 5. Rahul edits customer -> 200 OK
    res = client.put(f'/api/master_customers/{created_cust_id}', json={
        'name': 'Rahul Fresh Supermarket'
    })
    assert res.status_code == 200

    # 6. Rahul attempts to deploy a Saved Template -> 403 Forbidden
    res = client.post('/api/deploy_template/5?mode=deploy')
    assert res.status_code == 403

    # 7. Rahul attempts to create a driver -> 403 Forbidden
    res = client.post('/api/admin_create_driver', json={
        'name': 'Unauthorized Driver',
        'phone': '9998887776',
        'password': 'DriverPass123'
    })
    assert res.status_code == 403

    # 8. Rahul attempts to access User Management -> 403 Forbidden
    res = client.get('/api/admin/users')
    assert res.status_code == 403

    # 9. Admin adds templates.view and templates.deploy to Rahul's permissions
    login_user(client, admin)
    res = client.put(f'/api/admin/users/{rahul_id}/permissions', json={
        'permissions': ['customers.view', 'customers.create', 'customers.edit', 'templates.view', 'templates.deploy']
    })
    assert res.status_code == 200

    # 10. Rahul re-authenticates (session refreshed with new auth_version)
    with app.app_context():
        rahul = db.session.get(User, rahul_id)
    login_user(client, rahul)

    # Rahul deploys the template -> 200 OK!
    res = client.post('/api/deploy_template/5?mode=deploy')
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # 11. Admin deactivates Rahul
    login_user(client, admin)
    res = client.put(f'/api/admin/users/{rahul_id}/status', json={'is_active': False})
    assert res.status_code == 200

    # 12. Rahul's active session is rejected immediately on next request
    login_user(client, User(id=rahul_id, auth_version=rahul.auth_version))  # using previous auth_version before deactivation
    res = client.get('/api/master_customers')
    assert res.status_code in [401, 403]

    # 13. Rahul tries to log in again -> rejected
    client.get('/logout')
    res = client.post('/login', data={'username': 'rahul', 'password': 'RahulPassword123'})
    assert res.status_code == 200
    assert b'deactivated' in res.data or b'Invalid' in res.data
