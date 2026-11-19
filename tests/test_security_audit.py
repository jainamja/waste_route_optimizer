import unittest
import json
import io
import time
from werkzeug.security import generate_password_hash

import waste_route_optimizer as w
from waste_route_optimizer import (
    app, db, User, Customer, SavedTemplate,
    generate_auth_token, verify_auth_token
)

class TestSecurityAudit(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Admin user
        admin = User.query.filter_by(username='sec_admin').first()
        if not admin:
            admin = User(
                username='sec_admin',
                password_hash=generate_password_hash('AdminPass@2026'),
                role='ADMIN',
                name='Security Admin'
            )
            db.session.add(admin)
            db.session.commit()
        self.admin = admin

        # Driver 1 (truck 10)
        d1 = User.query.filter_by(username='sec_driver1').first()
        if not d1:
            d1 = User(
                username='sec_driver1',
                password_hash=generate_password_hash('Driver1Pass'),
                role='DRIVER',
                name='Security Driver 1',
                truck_id=10
            )
            db.session.add(d1)
        else:
            d1.truck_id = 10
        db.session.commit()
        self.driver1 = d1

        # Driver 2 (truck 20)
        d2 = User.query.filter_by(username='sec_driver2').first()
        if not d2:
            d2 = User(
                username='sec_driver2',
                password_hash=generate_password_hash('Driver2Pass'),
                role='DRIVER',
                name='Security Driver 2',
                truck_id=20
            )
            db.session.add(d2)
        else:
            d2.truck_id = 20
        db.session.commit()
        self.driver2 = d2

        # Test customer stops
        c1 = Customer.query.filter_by(id=99001).first()
        if not c1:
            c1 = Customer(
                id=99001,
                name='Sec Cust 1',
                phone='9999990001',
                address='Sec Address 1',
                lat=23.01,
                lng=72.51,
                status='PENDING',
                truck_id=10,
                stop_number=1
            )
            db.session.add(c1)
        else:
            c1.truck_id = 10
            c1.status = 'PENDING'

        c2 = Customer.query.filter_by(id=99002).first()
        if not c2:
            c2 = Customer(
                id=99002,
                name='Sec Cust 2',
                phone='9999990002',
                address='Sec Address 2',
                lat=23.02,
                lng=72.52,
                status='PENDING',
                truck_id=20,
                stop_number=1
            )
            db.session.add(c2)
        else:
            c2.truck_id = 20
            c2.status = 'PENDING'

        db.session.commit()
        self.cust1 = c1
        self.cust2 = c2

    def tearDown(self):
        self.ctx.pop()

    # --- 1. Token Cryptographic Signing & Validation ---
    def test_signed_token_generation_and_verification(self):
        token = generate_auth_token(self.admin)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 20)
        self.assertNotEqual(token, str(self.admin.id))

        verified = verify_auth_token(token)
        self.assertIsNotNone(verified)
        self.assertEqual(verified.id, self.admin.id)
        self.assertEqual(verified.role, 'ADMIN')

    def test_tampered_token_rejected(self):
        token = generate_auth_token(self.admin)
        tampered = token[:-5] + 'xxxxx'
        self.assertIsNone(verify_auth_token(tampered))

    def test_expired_token_rejected(self):
        token = generate_auth_token(self.admin)
        # Using negative max_age ensures token is treated as expired
        self.assertIsNone(verify_auth_token(token, max_age=-1))

    def test_empty_or_invalid_token_rejected(self):
        self.assertIsNone(verify_auth_token(None))
        self.assertIsNone(verify_auth_token(''))
        self.assertIsNone(verify_auth_token('not_a_valid_token_xyz'))

    # --- 2. Endpoint Protection & RBAC ---
    def test_unauthenticated_api_endpoints_return_401(self):
        res = self.client.get('/api/templates')
        self.assertEqual(res.status_code, 401)

        res_check = self.client.get('/api/admin_check')
        self.assertEqual(res_check.status_code, 401)

    def test_driver_token_cannot_access_admin_check(self):
        driver_token = generate_auth_token(self.driver1)
        res = self.client.get('/api/admin_check', headers={'X-Admin-Token': driver_token})
        self.assertIn(res.status_code, (401, 403))

    # --- 3. Stop Status Authorization & IDOR Prevention ---
    def test_unauthenticated_mark_stop_status_rejected(self):
        res = self.client.post('/api/mark_stop_status', json={
            'truck_id': 10,
            'stop_id': 99001,
            'status': 'COMPLETED'
        })
        self.assertEqual(res.status_code, 401)

    def test_driver_cannot_update_other_truck_stop(self):
        d1_token = generate_auth_token(self.driver1)
        # Driver 1 belongs to truck 10; trying to update truck 20 stops should be forbidden
        res = self.client.post(
            '/api/mark_stop_status',
            headers={'Authorization': f'Bearer {d1_token}'},
            json={
                'truck_id': 20,
                'stop_id': 99002,
                'status': 'COMPLETED'
            }
        )
        self.assertEqual(res.status_code, 403)

    def test_driver_can_update_own_truck_stop(self):
        d1_token = generate_auth_token(self.driver1)
        res = self.client.post(
            '/api/mark_stop_status',
            headers={'Authorization': f'Bearer {d1_token}'},
            json={
                'truck_id': 10,
                'driver_id': self.driver1.id,
                'stop_id': 99001,
                'status': 'COMPLETED'
            }
        )
        self.assertEqual(res.status_code, 200)
        c = db.session.get(Customer, 99001)
        self.assertEqual(c.status, 'COMPLETED')

    def test_invalid_stop_status_rejected(self):
        d1_token = generate_auth_token(self.driver1)
        res = self.client.post(
            '/api/mark_stop_status',
            headers={'Authorization': f'Bearer {d1_token}'},
            json={
                'truck_id': 10,
                'stop_id': 99001,
                'status': 'INVALID_STATUS_MALICIOUS'
            }
        )
        self.assertEqual(res.status_code, 400)

    # --- 4. File Upload Security ---
    def test_upload_unsupported_extension_rejected(self):
        admin_token = generate_auth_token(self.admin)
        data = {
            'file': (io.BytesIO(b'malicious script content'), 'exploit.sh'),
            'start_coords_json': json.dumps(['23.01,72.51']),
            'end_coords_json': json.dumps(['23.02,72.52']),
            'num_trucks': 1
        }
        res = self.client.post(
            '/upload',
            headers={'X-Admin-Token': admin_token},
            content_type='multipart/form-data',
            data=data
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('not supported', res.get_json().get('error', ''))

    # --- 5. Security Headers ---
    def test_security_headers_present(self):
        res = self.client.get('/healthz')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('X-XSS-Protection'), '1; mode=block')
        self.assertEqual(res.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')
        self.assertIn('frame-ancestors', res.headers.get('Content-Security-Policy', ''))

if __name__ == '__main__':
    unittest.main()
