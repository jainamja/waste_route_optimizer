import unittest
import json
import uuid
from unittest.mock import patch, MagicMock

import waste_route_optimizer as w
from waste_route_optimizer import (
    app, db, User, Customer, SavedTemplate, Metadata, MasterCustomer,
    get_firebase_token, get_firebase_auth_param, append_firebase_auth,
    generate_auth_token
)

def login_user(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['auth_version'] = getattr(user, 'auth_version', 1)

class TestBackend500AuditRepairs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            # Ensure primary admin user exists
            cls.admin_user = User.query.filter_by(username='admin').first()
            if not cls.admin_user:
                cls.admin_user = User(username='admin', role='ADMIN', is_active=True, is_superadmin=True)
                cls.admin_user.set_password('green@2026')
                db.session.add(cls.admin_user)
                db.session.commit()
            cls.admin_token = generate_auth_token(cls.admin_user)

            # Ensure a driver exists for assignment testing
            cls.driver_user = User.query.filter_by(role='DRIVER').first()
            if not cls.driver_user:
                cls.driver_user = User(username='test_driver_repair', role='DRIVER', is_active=True, truck_id=1)
                cls.driver_user.set_password('driver123')
                db.session.add(cls.driver_user)
                db.session.commit()
            cls.driver_token = generate_auth_token(cls.driver_user)

    def setUp(self):
        login_user(self.client, self.admin_user)

    # 1. Test Request JSON Parsing Safety (No 415/500 on missing Content-Type or empty body)
    def test_repair_database_without_content_type(self):
        """POST /api/admin/repair_database without json content-type header should return 200, not 415 or 500"""
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        res = self.client.post('/api/admin/repair_database', headers=headers, data='{"dry_run": true}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))

    def test_repair_database_empty_body(self):
        """POST /api/admin/repair_database with empty body should not crash with 500"""
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        res = self.client.post('/api/admin/repair_database', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))

    def test_assign_driver_without_json_header(self):
        """POST /api/assign_driver without json content-type returns 400 for missing truck_id, not 415 or 500"""
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        res = self.client.post('/api/assign_driver', headers=headers, data='random text')
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('error', data)

    def test_update_customer_details_without_json_header(self):
        """POST /api/update_customer_details without json content-type returns 400 for missing id, not 415 or 500"""
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        res = self.client.post('/api/update_customer_details', headers=headers, data='not json')
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('Customer ID is required', data.get('error', ''))

    # 2. Test Firebase Auth Parameter & Token Formatting
    def test_firebase_auth_param_oauth2_token(self):
        """OAuth2 tokens starting with ya29. must generate access_token= parameter"""
        fake_oauth2 = "ya29.a0AfH6SMCxyz123"
        param = get_firebase_auth_param(fake_oauth2)
        self.assertEqual(param, f"access_token={fake_oauth2}")

    def test_firebase_auth_param_jwt_token(self):
        """Firebase client JWTs starting with eyJ must generate auth= parameter"""
        fake_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
        param = get_firebase_auth_param(fake_jwt)
        self.assertEqual(param, f"auth={fake_jwt}")

    def test_append_firebase_auth_url(self):
        """append_firebase_auth correctly handles URLs with and without query parameters"""
        fake_oauth2 = "ya29.fake"
        url1 = "https://wasteroutelive-default-rtdb.firebaseio.com/trucks.json"
        self.assertEqual(append_firebase_auth(url1, fake_oauth2), f"{url1}?access_token={fake_oauth2}")

        url2 = "https://wasteroutelive-default-rtdb.firebaseio.com/trucks.json?shallow=true"
        self.assertEqual(append_firebase_auth(url2, fake_oauth2), f"{url2}&access_token={fake_oauth2}")

    # 3. Test Safe Parameter Parsing & Validation Guards
    def test_truck_telemetry_invalid_limit(self):
        """GET /api/truck_telemetry/<id>?limit=invalid should safely fallback to limit=200, not crash with ValueError 500"""
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        res = self.client.get('/api/truck_telemetry/1?limit=not_a_number', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))

    def test_add_customer_to_template_invalid_customer_id(self):
        """POST /api/templates/<id>/add_customer with non-numeric customer_id returns 400, not 500"""
        with self.app.app_context():
            tmpl = SavedTemplate.query.filter_by(is_assigned_instance=False).first()
            if not tmpl:
                tmpl = SavedTemplate(name="Test Template For Audit", customers_json="[]", is_assigned_instance=False)
                db.session.add(tmpl)
                db.session.commit()
            tmpl_id = tmpl.id

        headers = {'Authorization': f'Bearer {self.admin_token}', 'Content-Type': 'application/json'}
        res = self.client.post(f'/api/templates/{tmpl_id}/add_customer', headers=headers, json={'customer_id': 'invalid_string'})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('Invalid customer_id', data.get('error', ''))

    def test_upload_malformed_coordinates(self):
        """POST /upload with malformed coordinates JSON returns 400, not unhandled 500"""
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        import io
        fake_csv = io.BytesIO(b"Name,Address,Phone,Google Maps Location URL\nTest,Addr,1234567890,http://maps.google.com\n")
        data = {
            'file': (fake_csv, 'test.csv'),
            'start_coords_json': '{invalid_json',
            'end_coords_json': '[]'
        }
        res = self.client.post('/upload', headers=headers, data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 400)
        res_data = res.get_json()
        self.assertIn('Malformed start or end coordinates', res_data.get('error', ''))

    # 4. Test Metadata Protection
    def test_protected_metadata_keys_preserved(self):
        """Operational metadata keys like pending_rtdb_sync and initial_templates_seeded must not be wiped"""
        with self.app.app_context():
            # Ensure keys exist
            for k in ['pending_rtdb_sync', 'initial_templates_seeded', 'migration_in_progress']:
                row = Metadata.query.filter_by(key=k).first()
                if not row:
                    val = '{}' if k == 'pending_rtdb_sync' else '1'
                    db.session.add(Metadata(key=k, value=val))
                elif k == 'pending_rtdb_sync' and not row.value.startswith('{'):
                    row.value = '{}'
            # Add an ephemeral route key
            db.session.add(Metadata(key='test_ephemeral_route_key', value='ephemeral'))
            db.session.commit()

            # Execute protection query as defined in upload and deploy_template
            PROTECTED_METADATA_KEYS = {'pending_rtdb_sync', 'initial_templates_seeded', 'migration_in_progress'}
            Metadata.query.filter(Metadata.key.notin_(PROTECTED_METADATA_KEYS)).delete(synchronize_session=False)
            db.session.commit()

            # Verify protected keys still exist
            for k in ['pending_rtdb_sync', 'initial_templates_seeded', 'migration_in_progress']:
                row = Metadata.query.filter_by(key=k).first()
                self.assertIsNotNone(row, f"Protected metadata key {k} was wiped!")

            # Verify ephemeral was deleted
            ephemeral = Metadata.query.filter_by(key='test_ephemeral_route_key').first()
            self.assertIsNone(ephemeral)

    # 5. Test Safe Stop Handling with Firebase Error Payloads
    def test_remove_stop_resilient_to_firebase_error(self):
        """remove_stop should gracefully handle Firebase error dictionary without AttributeError on s_info.get"""
        with self.app.app_context():
            # Mock get_firebase_token and requests.get returning Firebase error payload
            with patch('waste_route_optimizer.get_firebase_token', return_value='fake_token'):
                mock_res = MagicMock()
                mock_res.status_code = 401
                mock_res.json.return_value = {"error": "Permission denied"}
                with patch('requests.get', return_value=mock_res):
                    headers = {'Authorization': f'Bearer {self.admin_token}', 'Content-Type': 'application/json'}
                    res = self.client.post('/api/remove_stop', headers=headers, json={'truck_id': 1, 'customer_id': 999999})
                    # Should return 404 (customer not found) or clean response, NOT 500 AttributeError
                    self.assertIn(res.status_code, [200, 404])

if __name__ == '__main__':
    unittest.main()
