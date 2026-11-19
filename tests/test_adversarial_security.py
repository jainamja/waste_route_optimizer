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

class TestAdversarialSecurity(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Admin user
        admin = User.query.filter_by(username='adv_admin').first()
        if not admin:
            admin = User(
                username='adv_admin',
                password_hash=generate_password_hash('AdvPass@2026'),
                role='ADMIN',
                name='Adversary Admin'
            )
            db.session.add(admin)
            db.session.commit()
        else:
            admin.password_hash = generate_password_hash('AdvPass@2026')
            admin.role = 'ADMIN'
            db.session.commit()
        self.admin = admin

        # Driver 1 (truck 101)
        d1 = User.query.filter_by(username='adv_driver1').first()
        if not d1:
            d1 = User(
                username='adv_driver1',
                password_hash=generate_password_hash('Driver1Pass'),
                role='DRIVER',
                name='Adv Driver 1',
                truck_id=101
            )
            db.session.add(d1)
        else:
            d1.truck_id = 101
            d1.password_hash = generate_password_hash('Driver1Pass')
            d1.role = 'DRIVER'
        db.session.commit()
        self.driver1 = d1

        # Driver 2 (truck 102)
        d2 = User.query.filter_by(username='adv_driver2').first()
        if not d2:
            d2 = User(
                username='adv_driver2',
                password_hash=generate_password_hash('Driver2Pass'),
                role='DRIVER',
                name='Adv Driver 2',
                truck_id=102
            )
            db.session.add(d2)
        else:
            d2.truck_id = 102
            d2.password_hash = generate_password_hash('Driver2Pass')
            d2.role = 'DRIVER'
        db.session.commit()
        self.driver2 = d2

        # Customer stop belonging to truck 101
        c1 = Customer.query.filter_by(id=88001).first()
        if not c1:
            c1 = Customer(
                id=88001,
                name='Adv Stop 1',
                phone='8888880001',
                address='Adv Address 1',
                lat=23.01,
                lng=72.51,
                status='PENDING',
                truck_id=101,
                stop_number=1
            )
            db.session.add(c1)
        else:
            c1.truck_id = 101
            c1.status = 'PENDING'

        # Customer stop belonging to truck 102
        c2 = Customer.query.filter_by(id=88002).first()
        if not c2:
            c2 = Customer(
                id=88002,
                name='Adv Stop 2',
                phone='8888880002',
                address='Adv Address 2',
                lat=23.02,
                lng=72.52,
                status='PENDING',
                truck_id=102,
                stop_number=1
            )
            db.session.add(c2)
        else:
            c2.truck_id = 102
            c2.status = 'PENDING'

        db.session.commit()
        self.cust1 = c1
        self.cust2 = c2

    def tearDown(self):
        self.ctx.pop()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            User.query.filter(User.username.in_(['adv_admin', 'adv_driver1', 'adv_driver2'])).delete()
            Customer.query.filter(Customer.truck_id.in_([101, 102])).delete()
            db.session.commit()

    # =========================================================================
    # 1. PREDICTABLE RAW NUMERIC ID ATTACKS (IDs: 1, 2, 100, 1000)
    # =========================================================================
    def test_raw_numeric_tokens_rejected_everywhere(self):
        predictable_ids = ['1', '2', '100', '1000', str(self.admin.id), str(self.driver1.id)]
        
        for pid in predictable_ids:
            # A. Direct verification function
            self.assertIsNone(verify_auth_token(pid), f"verify_auth_token must reject raw numeric ID {pid}")

            # B. Query parameter admin_token
            res = self.client.get(f'/api/templates?admin_token={pid}')
            self.assertEqual(res.status_code, 401, f"GET /api/templates?admin_token={pid} must return 401")

            # C. Header X-Admin-Token
            res = self.client.get('/api/templates', headers={'X-Admin-Token': pid})
            self.assertEqual(res.status_code, 401, f"GET /api/templates with header X-Admin-Token={pid} must return 401")

            # D. Admin token auth redirect
            res = self.client.get(f'/api/admin_token_auth?token={pid}&next=/dashboard')
            self.assertEqual(res.status_code, 302)
            self.assertIn('/login', res.headers.get('Location', ''), f"Numeric token {pid} must redirect to /login")

            # E. Resolve token endpoint
            res = self.client.get(f'/api/resolve_token?token={pid}')
            self.assertEqual(res.status_code, 401, f"GET /api/resolve_token?token={pid} must return 401")

            # F. Driver mark stop status
            res = self.client.post('/api/mark_stop_status', json={
                'truck_id': 101,
                'driver_id': pid,
                'stop_id': 88001,
                'status': 'COMPLETED'
            })
            self.assertEqual(res.status_code, 401, f"POST /api/mark_stop_status with numeric ID {pid} must return 401")

    # =========================================================================
    # 2. TOKEN REVOCATION & DYNAMIC STATE INVALIDATION
    # =========================================================================
    def test_password_change_revokes_active_tokens(self):
        """When a user changes their password, all previously generated tokens must be immediately rejected."""
        old_token = generate_auth_token(self.admin)
        self.assertIsNotNone(verify_auth_token(old_token))

        # Simulate password change
        self.admin.password_hash = generate_password_hash('NewPassword@2027')
        db.session.commit()

        # Old token must now be invalid!
        self.assertIsNone(verify_auth_token(old_token), "Token must be invalidated after password change")

        # Newly generated token with new password hash works
        new_token = generate_auth_token(self.admin)
        self.assertIsNotNone(verify_auth_token(new_token))

    def test_deactivated_or_deleted_user_token_rejected(self):
        """Tokens belonging to deleted or nonexistent users must fail even if cryptographically valid."""
        temp_user = User(
            username='temp_deleted_user',
            password_hash=generate_password_hash('TempPass'),
            role='DRIVER',
            truck_id=999
        )
        db.session.add(temp_user)
        db.session.commit()

        valid_token = generate_auth_token(temp_user)
        self.assertIsNotNone(verify_auth_token(valid_token))

        # Delete the user from the database
        db.session.delete(temp_user)
        db.session.commit()

        # Token must immediately fail
        self.assertIsNone(verify_auth_token(valid_token), "Token for deleted user must be rejected")

    def test_tampered_role_in_token_rejected(self):
        """If user's role is changed in database (e.g. demoted from ADMIN to DRIVER), old admin token fails."""
        token = generate_auth_token(self.admin)
        self.assertEqual(verify_auth_token(token).role, 'ADMIN')

        # Demote user in database
        self.admin.role = 'DRIVER'
        db.session.commit()

        # Old token claims role='ADMIN', but database says role='DRIVER' -> mismatch must be rejected!
        self.assertIsNone(verify_auth_token(token), "Role mismatch between token and live DB must fail")

        # Restore role
        self.admin.role = 'ADMIN'
        db.session.commit()

    # =========================================================================
    # 3. DRIVER CROSS-TRUCK IDOR ATTACKS
    # =========================================================================
    def test_driver1_cannot_update_driver2_stops(self):
        """Driver 1 (Truck 101) attempts to update stop 88002 belonging to Truck 102."""
        d1_token = generate_auth_token(self.driver1)
        res = self.client.post(
            '/api/mark_stop_status',
            headers={'Authorization': f'Bearer {d1_token}'},
            json={
                'truck_id': 102,
                'stop_id': 88002,
                'status': 'COMPLETED'
            }
        )
        self.assertEqual(res.status_code, 403, "Driver cannot update stops belonging to another truck")
        
        # Verify customer in DB was NOT updated
        c2 = db.session.get(Customer, 88002)
        self.assertEqual(c2.status, 'PENDING')

    def test_driver1_cannot_finish_driver2_route(self):
        """Driver 1 attempts to finish Driver 2's route."""
        d1_token = generate_auth_token(self.driver1)
        res = self.client.post(
            '/api/driver_finish_route',
            headers={'Authorization': f'Bearer {d1_token}'},
            json={'truck_id': 102, 'driver_id': self.driver1.id}
        )
        # Should be forbidden or unauthorized because driver1 belongs to truck 101
        self.assertIn(res.status_code, (401, 403))

    # =========================================================================
    # 4. MALICIOUS FILE UPLOAD & INJECTION ATTACKS
    # =========================================================================
    def test_spoofed_mime_type_executable_rejected(self):
        """An attacker uploads an executable binary disguised with a .xlsx extension."""
        admin_token = generate_auth_token(self.admin)
        fake_excel_bytes = b'\x4d\x5a\x90\x00\x03\x00\x00\x00' # MZ DOS/PE executable header
        data = {
            'file': (io.BytesIO(fake_excel_bytes), 'malware.xlsx'),
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
        self.assertIn('spoofed', res.get_json().get('error', '').lower())

    def test_spoofed_binary_csv_rejected(self):
        """An attacker uploads binary shellcode disguised as a .csv file."""
        admin_token = generate_auth_token(self.admin)
        fake_csv_bytes = b'name,address\x00\x01\x02\x03malicious_binary'
        data = {
            'file': (io.BytesIO(fake_csv_bytes), 'exploit.csv'),
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
        self.assertIn('binary', res.get_json().get('error', '').lower())

    def test_excel_formula_injection_sanitization(self):
        """Verify formula injection triggers (=, +, -, @) are sanitized with leading single quote on download."""
        # Insert customer with formula payload
        malicious_cust = Customer.query.filter_by(id=77001).first()
        if not malicious_cust:
            malicious_cust = Customer(
                id=77001,
                name='=cmd|\'/C calc\'!A0',
                phone='@SUM(1+1)',
                address='-2+3+cmd|',
                location_url='+https://malicious.com',
                lat=23.05,
                lng=72.55,
                status='PENDING',
                truck_id=1,
                stop_number=1
            )
            db.session.add(malicious_cust)
            db.session.commit()

        admin_token = generate_auth_token(self.admin)
        res = self.client.get(f'/download_excel?admin_token={admin_token}')
        self.assertEqual(res.status_code, 200)

        # Parse downloaded excel file and inspect cells
        import pandas as pd
        excel_io = io.BytesIO(res.data)
        df = pd.read_excel(excel_io)
        
        row = df[df['name'].astype(str).str.contains('calc')].iloc[0]
        # Must start with single quote "'" to neutralize spreadsheet formula execution
        self.assertTrue(str(row['name']).startswith("'="), f"Formula injection not neutralized: {row['name']}")
        self.assertTrue(str(row['phone']).startswith("'@"), f"Formula injection not neutralized: {row['phone']}")
        self.assertTrue(str(row['address']).startswith("'-"), f"Formula injection not neutralized: {row['address']}")
        self.assertTrue(str(row['location_url']).startswith("'+"), f"Formula injection not neutralized: {row['location_url']}")

if __name__ == '__main__':
    unittest.main()
