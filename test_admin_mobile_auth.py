import unittest
import json
from werkzeug.security import generate_password_hash

import waste_route_optimizer as w
from waste_route_optimizer import app, db, User, Customer, SavedTemplate

class TestAdminMobileAuth(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Ensure admin user exists
        admin = User.query.filter_by(username='test_admin').first()
        if not admin:
            admin = User(
                username='test_admin',
                password_hash=generate_password_hash('adminpass123'),
                role='ADMIN',
                name='Test Admin'
            )
            db.session.add(admin)
            db.session.commit()
        self.admin = admin

        # Ensure driver user exists
        driver = User.query.filter_by(username='test_driver').first()
        if not driver:
            driver = User(
                username='test_driver',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Test Driver',
                truck_id=99
            )
            db.session.add(driver)
        else:
            driver.truck_id = 99
            driver.password_hash = generate_password_hash('driverpass123')
        db.session.commit()
        self.driver = driver

    def tearDown(self):
        self.ctx.pop()

    def test_admin_login_via_mobile_endpoint(self):
        res = self.client.post('/api/driver_login', json={
            'username': 'test_admin',
            'password': 'adminpass123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['role'], 'ADMIN')
        self.assertEqual(data['user_id'], self.admin.id)
        self.assertTrue(len(data['token']) > 15, "Token must be a secure signed token string, not raw integer ID")
        from waste_route_optimizer import verify_auth_token
        auth_user = verify_auth_token(data['token'])
        self.assertIsNotNone(auth_user)
        self.assertEqual(auth_user.id, self.admin.id)
        self.assertIn('auth_url', data)
        self.assertIn(data['token'], data['auth_url'])

    def test_case_insensitive_and_whitespace_admin_login(self):
        # Capitalized username with leading/trailing spaces and password with accidental space
        res = self.client.post('/api/driver_login', json={
            'username': '  Test_Admin  ',
            'password': 'adminpass123 '
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['role'], 'ADMIN')
        self.assertEqual(data['user_id'], self.admin.id)
        from waste_route_optimizer import verify_auth_token
        auth_user = verify_auth_token(data['token'])
        self.assertIsNotNone(auth_user)
        self.assertEqual(auth_user.id, self.admin.id)

    def test_driver_login_via_mobile_endpoint(self):
        res = self.client.post('/api/driver_login', json={
            'username': 'test_driver',
            'password': 'driverpass123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['role'], 'DRIVER')
        self.assertEqual(data['user_id'], self.driver.id)
        self.assertEqual(data['truck_id'], '99')
        from waste_route_optimizer import verify_auth_token
        auth_driver = verify_auth_token(data['token'])
        self.assertIsNotNone(auth_driver)
        self.assertEqual(auth_driver.id, self.driver.id)

    def test_invalid_login_credentials(self):
        res = self.client.post('/api/driver_login', json={
            'username': 'test_admin',
            'password': 'wrongpassword'
        })
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn('error', data)

    def test_admin_token_auth_redirect(self):
        from waste_route_optimizer import generate_auth_token
        token = generate_auth_token(self.admin)
        res = self.client.get(f'/api/admin_token_auth?token={token}&next=/dashboard')
        self.assertEqual(res.status_code, 302)
        self.assertIn(f'/dashboard?admin_token={token}', res.headers.get('Location', ''))
        
        # Verify session was set
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('user_id'), self.admin.id)

    def test_protected_endpoint_with_admin_token_param(self):
        # Without token -> 401 Unauthorized for JSON/API
        res_unauth = self.client.get('/api/templates')
        self.assertEqual(res_unauth.status_code, 401)

        from waste_route_optimizer import generate_auth_token
        token = generate_auth_token(self.admin)
        # With valid signed admin_token query parameter -> 200 OK
        res_auth = self.client.get(f'/api/templates?admin_token={token}')
        self.assertEqual(res_auth.status_code, 200)

        # Raw integer ID MUST fail with 401
        res_raw_id = self.client.get(f'/api/templates?admin_token={self.admin.id}')
        self.assertEqual(res_raw_id.status_code, 401)

    def test_protected_endpoint_with_admin_token_header(self):
        from waste_route_optimizer import generate_auth_token
        token = generate_auth_token(self.admin)
        # With valid signed X-Admin-Token header -> 200 OK
        res_header = self.client.get('/api/templates', headers={'X-Admin-Token': token})
        self.assertEqual(res_header.status_code, 200)

        # Raw integer ID in header MUST fail with 401
        res_raw_header = self.client.get('/api/templates', headers={'X-Admin-Token': str(self.admin.id)})
        self.assertEqual(res_raw_header.status_code, 401)

    def test_app_user_info_endpoint(self):
        from waste_route_optimizer import generate_auth_token
        token = generate_auth_token(self.admin)
        res = self.client.get(f'/api/app_user_info?admin_token={token}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['authenticated'])
        self.assertEqual(data['role'], 'ADMIN')
        self.assertEqual(data['username'], 'test_admin')

        # Raw integer ID MUST fail with 401
        res_raw = self.client.get(f'/api/app_user_info?admin_token={self.admin.id}')
        self.assertEqual(res_raw.status_code, 401)

if __name__ == '__main__':
    unittest.main()
