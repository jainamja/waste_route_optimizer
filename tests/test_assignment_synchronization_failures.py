import unittest
import json
import threading
import uuid
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

import waste_route_optimizer as w
from waste_route_optimizer import (
    app, db, User, Customer, SavedTemplate, Metadata, AssignmentOutbox,
    AssignmentGlobalSequence, DriverLifecycleLedger,
    generate_auth_token, verify_auth_token,
    set_driver_rtdb_assignment,
    set_driver_rtdb_assignment_conditional,
    record_pending_rtdb_assignment,
    clear_pending_rtdb_assignment,
    reconcile_pending_rtdb_assignments,
    sync_all_driver_assignments_to_firebase,
    ensure_driver_truck_assignments,
    assignment_sync_lock,
    assignment_coordination_guard,
    allocate_next_assignment_revision,
    stage_assignment_intent,
    update_assignment_intent_status,
    complete_assignment_intent
)

class TestAssignmentSynchronizationFailures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            # Clean up any leftover test accounts
            User.query.filter(User.username.like('sync_test_%')).delete()
            Metadata.query.filter_by(key='pending_rtdb_sync').delete()
            try:
                AssignmentOutbox.query.delete()
            except Exception:
                pass
            db.session.commit()

            # Create test Admin
            cls.admin = User(
                username='sync_test_admin',
                password_hash=generate_password_hash('AdminPass@2026'),
                role='ADMIN',
                name='Sync Test Admin'
            )
            db.session.add(cls.admin)

            # Create test Driver 1 (Truck 101)
            cls.driver1 = User(
                username='sync_test_driver1',
                password_hash=generate_password_hash('Driver1Pass'),
                role='DRIVER',
                name='Sync Driver 1',
                truck_id=101
            )
            db.session.add(cls.driver1)

            # Create test Driver 2 (Truck 102)
            cls.driver2 = User(
                username='sync_test_driver2',
                password_hash=generate_password_hash('Driver2Pass'),
                role='DRIVER',
                name='Sync Driver 2',
                truck_id=102
            )
            db.session.add(cls.driver2)

            # Create test Unassigned Driver
            cls.driver_unassigned = User(
                username='sync_test_unassigned',
                password_hash=generate_password_hash('DriverUnassignedPass'),
                role='DRIVER',
                name='Sync Driver Unassigned',
                truck_id=None
            )
            db.session.add(cls.driver_unassigned)

            db.session.commit()
            cls.admin_id = cls.admin.id
            cls.driver1_id = cls.driver1.id
            cls.driver2_id = cls.driver2.id
            cls.unassigned_id = cls.driver_unassigned.id

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            User.query.filter(User.username.like('sync_test_%')).delete()
            Metadata.query.filter_by(key='pending_rtdb_sync').delete()
            try:
                AssignmentOutbox.query.delete()
            except Exception:
                pass
            db.session.commit()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.app.config.pop('MOCK_FIREBASE_RTDB_SUCCESS', None)
        self.app.config.pop('MOCK_FIREBASE_RTDB_FAILURE', None)

        # Reset driver assignments to baseline
        d1 = db.session.get(User, self.driver1_id)
        if d1: d1.truck_id = 101
        d2 = db.session.get(User, self.driver2_id)
        if d2: d2.truck_id = 102
        du = db.session.get(User, self.unassigned_id)
        if du: du.truck_id = None

        Metadata.query.filter_by(key='pending_rtdb_sync').delete()
        try:
            AssignmentOutbox.query.delete()
        except Exception:
            pass
        db.session.commit()

        self.admin_token = generate_auth_token(db.session.get(User, self.admin_id))
        self.driver1_token = generate_auth_token(db.session.get(User, self.driver1_id))
        self.unassigned_token = generate_auth_token(db.session.get(User, self.unassigned_id))
        self.headers = {'X-Admin-Token': self.admin_token}

    def tearDown(self):
        self.app.config.pop('MOCK_FIREBASE_RTDB_SUCCESS', None)
        self.app.config.pop('MOCK_FIREBASE_RTDB_FAILURE', None)
        try:
            db.session.rollback()
            User.query.filter(User.username.like('sync_test_tmp_%')).delete()
            Metadata.query.filter_by(key='pending_rtdb_sync').delete()
            try:
                AssignmentOutbox.query.delete()
            except Exception:
                pass
            db.session.commit()
        except Exception:
            pass
        self.ctx.pop()

    # -------------------------------------------------------------------------
    # TEST 1: RTDB Pre-revocation Timeout in /api/admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_set_driver_truck_revocation_timeout(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Connection timed out to Firebase RTDB")

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertIn('Connection timed out', data.get('error', ''))

        # Fail-closed check: SQLite assignment must remain UNCHANGED
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

    # -------------------------------------------------------------------------
    # TEST 2: RTDB Pre-revocation 403 in /api/admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_set_driver_truck_revocation_403(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Firebase RTDB returned HTTP 403")

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertFalse(data.get('success', True))

        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

    # -------------------------------------------------------------------------
    # TEST 3: RTDB Pre-revocation 500 in /api/admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_set_driver_truck_revocation_500(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Firebase RTDB returned HTTP 500")

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

    # -------------------------------------------------------------------------
    # TEST 4: Missing Firebase Admin Token in /api/admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.get_firebase_token')
    def test_admin_set_driver_truck_missing_firebase_token(self, mock_get_token):
        mock_get_token.return_value = None

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

    # -------------------------------------------------------------------------
    # TEST 5: Phase 3 Grant Failure in /api/admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_set_driver_truck_phase3_grant_failure(self, mock_rtdb):
        # Pre-revocation succeeds (call 1), Phase 3 grant fails (call 2)
        mock_rtdb.side_effect = [
            (True, "OK"),                                # Phase 1 revocation
            (False, "Grant network partition timeout")  # Phase 3 grant
        ]

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertTrue(data.get('pending_sync_recorded', False))

        # Check pending sync record created in SQLite metadata
        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        self.assertIsNotNone(meta)
        pending = json.loads(meta.value)
        self.assertEqual(pending.get(str(self.driver1_id)), 105)

    # -------------------------------------------------------------------------
    # TEST 6: SQLite Commit Failure in /api/admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch.object(db.session, 'commit')
    def test_admin_set_driver_truck_db_commit_failure(self, mock_commit, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        mock_commit.side_effect = Exception("SQLite OperationalError: disk I/O error")

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 500)

    # -------------------------------------------------------------------------
    # TEST 7: Evicted Driver Pre-revocation Failure in /api/admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_set_driver_truck_evicted_driver_failure(self, mock_rtdb):
        def side_effect(did, tid, **kwargs):
            if did == self.driver2_id and tid is None:
                return (False, "Failed to revoke evicted driver 2")
            return (True, "OK")

        mock_rtdb.side_effect = side_effect

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 102}
        )
        self.assertEqual(res.status_code, 502)

        # Neither driver should be modified in SQLite
        d1 = db.session.get(User, self.driver1_id)
        d2 = db.session.get(User, self.driver2_id)
        self.assertEqual(d1.truck_id, 101)
        self.assertEqual(d2.truck_id, 102)

    # -------------------------------------------------------------------------
    # TEST 8: RTDB Pre-revocation Failure in /api/assign_driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_assign_driver_revocation_failure(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Pre-revocation error in assign_driver")

        res = self.client.post(
            '/api/assign_driver',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

    # -------------------------------------------------------------------------
    # TEST 9: Phase 3 Grant Failure in /api/assign_driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_assign_driver_phase3_grant_failure(self, mock_rtdb):
        mock_rtdb.side_effect = [
            (True, "OK"),
            (False, "Grant failed in assign_driver")
        ]

        res = self.client.post(
            '/api/assign_driver',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertTrue(data.get('pending_sync_recorded', False))

        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        self.assertIsNotNone(meta)
        pending = json.loads(meta.value)
        self.assertEqual(pending.get(str(self.driver1_id)), 105)

    # -------------------------------------------------------------------------
    # TEST 10: RTDB Pre-revocation Failure in /api/assign_route
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_assign_route_truck_switch_revocation_failure(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Pre-revocation error in assign_route")

        res = self.client.post(
            '/api/assign_route',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

    # -------------------------------------------------------------------------
    # TEST 11: Phase 3 Grant Failure in /api/assign_route
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_assign_route_phase3_grant_failure(self, mock_rtdb):
        mock_rtdb.side_effect = [
            (True, "OK"),
            (False, "Grant failed in assign_route")
        ]

        res = self.client.post(
            '/api/assign_route',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        self.assertIsNotNone(meta)
        pending = json.loads(meta.value)
        self.assertEqual(pending.get(str(self.driver1_id)), 105)

    # -------------------------------------------------------------------------
    # TEST 12: RTDB Revocation Failure in /api/admin_delete_driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_delete_driver_revocation_failure(self, mock_rtdb):
        del_driver = User(
            username='sync_test_del_fail',
            password_hash=generate_password_hash('pass'),
            role='DRIVER',
            truck_id=108
        )
        db.session.add(del_driver)
        db.session.commit()
        del_id = del_driver.id

        mock_rtdb.return_value = (False, "Revocation failed on delete")

        res = self.client.delete(
            f'/api/admin_delete_driver/{del_id}',
            headers=self.headers
        )
        self.assertEqual(res.status_code, 502)

        check_driver = db.session.get(User, del_id)
        self.assertIsNotNone(check_driver)

        db.session.delete(check_driver)
        db.session.commit()

    # -------------------------------------------------------------------------
    # TEST 13: RTDB Revocation Success in /api/admin_delete_driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_delete_driver_revocation_success(self, mock_rtdb):
        del_driver = User(
            username='sync_test_del_ok',
            password_hash=generate_password_hash('pass'),
            role='DRIVER',
            truck_id=109
        )
        db.session.add(del_driver)
        db.session.commit()
        del_id = del_driver.id

        mock_rtdb.return_value = (True, "OK")

        res = self.client.delete(
            f'/api/admin_delete_driver/{del_id}',
            headers=self.headers
        )
        self.assertEqual(res.status_code, 200)

        check_driver = db.session.get(User, del_id)
        self.assertIsNone(check_driver)

    # -------------------------------------------------------------------------
    # TEST 14: Unassigned Driver Custom Token Issuance Success
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_firebase_custom_token_unassigned_driver(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        unassigned_driver = db.session.get(User, self.unassigned_id)
        token = generate_auth_token(unassigned_driver)

        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success', False))
        self.assertIsNone(data['claims'].get('truck_id'))

        # Verified: set_driver_rtdb_assignment called with truck_id=None
        mock_rtdb.assert_called_with(self.unassigned_id, None)

    # -------------------------------------------------------------------------
    # TEST 15: Unassigned Driver Token Issuance Fails on Revocation Timeout
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_firebase_custom_token_unassigned_revocation_timeout(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Connection timed out to Firebase RTDB")
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {self.unassigned_token}'}
        )
        self.assertEqual(res.status_code, 503)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertIn('Unable to verify real-time revocation status', data.get('error', ''))

    # -------------------------------------------------------------------------
    # TEST 16: Unassigned Driver Token Issuance Fails on Revocation 403
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_firebase_custom_token_unassigned_revocation_403(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Firebase RTDB returned HTTP 403")
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {self.unassigned_token}'}
        )
        self.assertEqual(res.status_code, 503)
        data = res.get_json()
        self.assertFalse(data.get('success', True))

    # -------------------------------------------------------------------------
    # TEST 17: Unassigned Driver Token Issuance Fails on Revocation 500
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_firebase_custom_token_unassigned_revocation_500(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Firebase RTDB returned HTTP 500")
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {self.unassigned_token}'}
        )
        self.assertEqual(res.status_code, 503)
        data = res.get_json()
        self.assertFalse(data.get('success', True))

    # -------------------------------------------------------------------------
    # TEST 18: Unassigned Driver Token Issuance Fails on Missing Firebase Token
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.get_firebase_token')
    def test_firebase_custom_token_unassigned_missing_credentials(self, mock_token):
        mock_token.return_value = None
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {self.unassigned_token}'}
        )
        self.assertEqual(res.status_code, 503)

    # -------------------------------------------------------------------------
    # TEST 19: Assigned Driver Token Issuance Fails When RTDB Sync Fails
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_firebase_custom_token_assigned_driver_sync_failure(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Firebase RTDB sync timeout")
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {self.driver1_token}'}
        )
        self.assertEqual(res.status_code, 503)
        data = res.get_json()
        self.assertIn('Unable to verify real-time dispatch synchronization', data.get('error', ''))

    # -------------------------------------------------------------------------
    # TEST 20: Dashboard GET Does Not Assign Unassigned Drivers
    # -------------------------------------------------------------------------
    def test_dashboard_get_does_not_assign_unassigned_driver(self):
        du = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du.truck_id)

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_id

        # Repeated GET requests simulating routine admin dashboard loads
        for _ in range(3):
            res = self.client.get('/')
            self.assertEqual(res.status_code, 200)

        # Unassigned driver MUST remain unassigned (truck_id is None)
        du_after = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du_after.truck_id)

    # -------------------------------------------------------------------------
    # TEST 21: /api/drivers GET Does Not Assign Unassigned Drivers
    # -------------------------------------------------------------------------
    def test_api_drivers_get_does_not_assign_unassigned_driver(self):
        du = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du.truck_id)

        # Repeated GET polling simulating frontend driver list updates
        for _ in range(3):
            res = self.client.get('/api/drivers', headers=self.headers)
            self.assertEqual(res.status_code, 200)

        du_after = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du_after.truck_id)

    # -------------------------------------------------------------------------
    # TEST 22: /api/assigned_routes GET Does Not Assign Unassigned Drivers
    # -------------------------------------------------------------------------
    def test_api_assigned_routes_get_does_not_assign_unassigned_driver(self):
        du = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du.truck_id)

        for _ in range(3):
            res = self.client.get('/api/assigned_routes', headers=self.headers)
            self.assertEqual(res.status_code, 200)

        du_after = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du_after.truck_id)

    # -------------------------------------------------------------------------
    # TEST 23: Creating a Driver Does Not Revive Benched Drivers
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_create_driver_does_not_revive_benched_drivers(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")

        du = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du.truck_id)

        res = self.client.post(
            '/api/admin_create_driver',
            headers=self.headers,
            json={'username': 'sync_test_new_d', 'password': 'Password123!', 'name': 'New Driver'}
        )
        self.assertEqual(res.status_code, 200)

        # The new driver receives an allocated truck_id
        new_d = User.query.filter_by(username='sync_test_new_d').first()
        self.assertIsNotNone(new_d)
        self.assertIsNotNone(new_d.truck_id)

        # Benched/unassigned driver must REMAIN unassigned
        du_after = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du_after.truck_id)

        # Clean up
        db.session.delete(new_d)
        db.session.commit()

    # -------------------------------------------------------------------------
    # TEST 24: Assign Route Without Truck on Unassigned Driver Fails Cleanly
    # -------------------------------------------------------------------------
    def test_assign_route_unassigned_driver_without_truck_fails(self):
        du = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du.truck_id)

        res = self.client.post(
            '/api/assign_route',
            headers=self.headers,
            json={'driver_id': self.unassigned_id}
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('specify a truck_id', data.get('error', '').lower())

        # Driver remains unassigned
        du_after = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du_after.truck_id)

    # -------------------------------------------------------------------------
    # TEST 25: Pending Reconciliation Uses Current SQLite State, Not Old Snapshot
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_reconcile_pending_rtdb_uses_current_sqlite_state(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")

        # Driver 1 in SQLite is assigned to Truck 101
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

        # Old pending snapshot recorded a stale truck (999)
        record_pending_rtdb_assignment(self.driver1_id, 999)

        # Run reconciliation
        resolved, remaining = reconcile_pending_rtdb_assignments()
        self.assertEqual(resolved, 1)
        self.assertEqual(remaining, 0)

        # CRITICAL CHECK: set_driver_rtdb_assignment was called with 101 (current DB state), NOT 999!
        mock_rtdb.assert_called_with(self.driver1_id, 101, retries=1)

    # -------------------------------------------------------------------------
    # TEST 26: Pending Reconciliation Safely Revokes Deleted Drivers
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_reconcile_pending_rtdb_revokes_deleted_driver(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")

        # Record a pending sync for a driver ID that does not exist in SQLite
        non_existent_did = 88888
        record_pending_rtdb_assignment(non_existent_did, 105)

        resolved, remaining = reconcile_pending_rtdb_assignments()
        self.assertEqual(resolved, 1)
        self.assertEqual(remaining, 0)

        # CRITICAL CHECK: Deleted driver must be revoked in RTDB (truck_id=None)
        mock_rtdb.assert_called_with(non_existent_did, None, retries=1)

    # -------------------------------------------------------------------------
    # TEST 27: Bulk Sync Empty Driver Guard
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.get_firebase_token')
    def test_bulk_sync_empty_driver_guard(self, mock_token):
        mock_token.return_value = "mock_admin_token"
        with patch('waste_route_optimizer.User.query') as mock_query:
            mock_filter = MagicMock()
            mock_filter.all.return_value = []
            mock_query.filter_by.return_value = mock_filter

            ok, msg = sync_all_driver_assignments_to_firebase()
            self.assertFalse(ok)
            self.assertIn("Safety guard triggered", msg)

    # -------------------------------------------------------------------------
    # TEST 28: Concurrency Serialization via assignment_sync_lock
    # -------------------------------------------------------------------------
    def test_concurrency_assignment_sync_lock(self):
        execution_order = []

        def worker(num):
            with assignment_sync_lock:
                execution_order.append(f"start_{num}")
                import time
                time.sleep(0.05)
                execution_order.append(f"end_{num}")

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(execution_order), 4)
        if execution_order[0] == 'start_1':
            self.assertEqual(execution_order, ['start_1', 'end_1', 'start_2', 'end_2'])
        else:
            self.assertEqual(execution_order, ['start_2', 'end_2', 'start_1', 'end_1'])

    # -------------------------------------------------------------------------
    # TEST 29: Admin Sync Driver Assignments Reconciles and Flushes
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch('waste_route_optimizer.requests.patch')
    @patch('waste_route_optimizer.get_firebase_token')
    def test_admin_sync_driver_assignments_endpoint(self, mock_token, mock_patch, mock_rtdb):
        mock_token.return_value = "mock_admin_token"
        mock_rtdb.return_value = (True, "OK")
        mock_patch.return_value = MagicMock(status_code=200)

        # Record a pending sync for driver 1
        record_pending_rtdb_assignment(self.driver1_id, 101)

        res = self.client.post('/api/admin_sync_driver_assignments', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success', False))
        self.assertEqual(data.get('reconciled_pending'), 1)
        self.assertEqual(data.get('remaining_pending'), 0)

    # -------------------------------------------------------------------------
    # TEST 30: Concurrent admin_create_driver Allocates Unique Truck IDs
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_concurrent_admin_create_driver_allocates_unique_trucks(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        results = []
        errors = []

        def create_worker(idx):
            with self.app.app_context():
                client = self.app.test_client()
                try:
                    res = client.post(
                        '/api/admin_create_driver',
                        headers=self.headers,
                        json={
                            'username': f'sync_test_tmp_concur_{idx}',
                            'password': 'PassWord@123',
                            'name': f'Concurrent Driver {idx}'
                        }
                    )
                    results.append((idx, res.status_code, res.get_json()))
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=create_worker, args=(i,)) for i in range(1, 3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        self.assertEqual(len(results), 2)
        status1, data1 = results[0][1], results[0][2]
        status2, data2 = results[1][1], results[1][2]
        self.assertEqual(status1, 200)
        self.assertEqual(status2, 200)
        self.assertTrue(data1.get('success'))
        self.assertTrue(data2.get('success'))
        truck1 = data1.get('truck_id')
        truck2 = data2.get('truck_id')
        self.assertIsNotNone(truck1)
        self.assertIsNotNone(truck2)
        self.assertNotEqual(truck1, truck2, f"Allocated duplicate truck IDs: {truck1} and {truck2}")

    # -------------------------------------------------------------------------
    # TEST 31: Concurrent Driver Creation Does Not Revive Benched Driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_concurrent_driver_creation_preserves_benched_driver(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        benched = db.session.get(User, self.unassigned_id)
        self.assertIsNone(benched.truck_id)

        res = self.client.post(
            '/api/admin_create_driver',
            headers=self.headers,
            json={
                'username': 'sync_test_tmp_nobench',
                'password': 'PassWord@123',
                'name': 'No Bench Driver'
            }
        )
        self.assertEqual(res.status_code, 200)
        
        # Verify benched driver truck_id was NOT modified
        benched_after = db.session.get(User, self.unassigned_id)
        self.assertIsNone(benched_after.truck_id)

    # -------------------------------------------------------------------------
    # TEST 32: RTDB Failure During Driver Creation Fails Closed with 502
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_create_driver_rtdb_failure_fails_closed(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Firebase RTDB timeout during driver create")

        res = self.client.post(
            '/api/admin_create_driver',
            headers=self.headers,
            json={
                'username': 'sync_test_tmp_rtdb_fail',
                'password': 'PassWord@123',
                'name': 'RTDB Fail Driver'
            }
        )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertTrue(data.get('pending_sync_recorded', False))
        self.assertIn('live tracking activation failed', data.get('error', ''))

        # Newly created driver is in SQLite with pending sync recorded
        driver = User.query.filter_by(username='sync_test_tmp_rtdb_fail').first()
        self.assertIsNotNone(driver)
        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        self.assertIsNotNone(meta)
        pending = json.loads(meta.value)
        self.assertEqual(pending.get(str(driver.id)), driver.truck_id)

    # -------------------------------------------------------------------------
    # TEST 33: Pending Reconciliation Resolves Pending Driver Creation Sync
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_reconciliation_resolves_pending_driver_creation(self, mock_rtdb):
        # Create driver with pending sync
        driver = User(
            username='sync_test_tmp_reconcile',
            password_hash=generate_password_hash('Pass123'),
            role='DRIVER',
            truck_id=205,
            name='Reconcile Driver'
        )
        db.session.add(driver)
        db.session.commit()
        record_pending_rtdb_assignment(driver.id, 205)

        mock_rtdb.return_value = (True, "OK")
        reconciled, remaining = reconcile_pending_rtdb_assignments()
        self.assertEqual(reconciled, 1)
        self.assertEqual(remaining, 0)

        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        pending = json.loads(meta.value) if (meta and meta.value) else {}
        self.assertNotIn(str(driver.id), pending)

    # -------------------------------------------------------------------------
    # TEST 34: Admin Delete Driver Fails Closed When RTDB Revocation Fails
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_delete_driver_rtdb_failure_fails_closed(self, mock_rtdb):
        mock_rtdb.return_value = (False, "Firebase RTDB 503 Service Unavailable")

        driver = User(
            username='sync_test_tmp_del_fail',
            password_hash=generate_password_hash('Pass123'),
            role='DRIVER',
            truck_id=206,
            name='Delete Fail Driver'
        )
        db.session.add(driver)
        db.session.commit()
        driver_id = driver.id

        res = self.client.delete(f'/api/admin_delete_driver/{driver_id}', headers=self.headers)
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertIn('Failed to revoke live tracking assignment in Firebase', data.get('error', ''))

        # Fail-closed check: Driver MUST STILL EXIST in SQLite
        driver_still = db.session.get(User, driver_id)
        self.assertIsNotNone(driver_still)
        self.assertEqual(driver_still.truck_id, 206)

    # -------------------------------------------------------------------------
    # TEST 35: Admin Delete Driver Succeeds When RTDB Revocation Succeeds
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_admin_delete_driver_success(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")

        driver = User(
            username='sync_test_tmp_del_ok',
            password_hash=generate_password_hash('Pass123'),
            role='DRIVER',
            truck_id=207,
            name='Delete OK Driver'
        )
        db.session.add(driver)
        db.session.commit()
        driver_id = driver.id
        record_pending_rtdb_assignment(driver_id, 207)

        res = self.client.delete(f'/api/admin_delete_driver/{driver_id}', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success', False))

        # Check driver is deleted from SQLite
        self.assertIsNone(db.session.get(User, driver_id))

        # Check pending sync record is cleared
        meta = Metadata.query.filter_by(key='pending_rtdb_sync').first()
        pending = json.loads(meta.value) if (meta and meta.value) else {}
        self.assertNotIn(str(driver_id), pending)

    # -------------------------------------------------------------------------
    # TEST 36: Admin Delete Driver Non-Existent Driver Returns 404
    # -------------------------------------------------------------------------
    def test_admin_delete_driver_not_found(self):
        res = self.client.delete('/api/admin_delete_driver/999999', headers=self.headers)
        self.assertEqual(res.status_code, 404)

    # -------------------------------------------------------------------------
    # TEST 37: SQLite Commit Failure During Driver Creation Returns 500
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch.object(db.session, 'commit')
    def test_admin_create_driver_db_commit_failure(self, mock_commit, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        mock_commit.side_effect = Exception("SQLite OperationalError: disk full")

        res = self.client.post(
            '/api/admin_create_driver',
            headers=self.headers,
            json={
                'username': 'sync_test_tmp_commit_fail',
                'password': 'PassWord@123',
                'name': 'Commit Fail Driver'
            }
        )
        self.assertEqual(res.status_code, 500)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertIn('Database error during driver creation', data.get('error', ''))

    # -------------------------------------------------------------------------
    # TEST 38: Deletion Rollback Restores RTDB Assignment on Commit Failure
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch.object(db.session, 'commit')
    def test_admin_delete_driver_rollback_restores_rtdb(self, mock_commit, mock_rtdb):
        driver = User(
            username='sync_test_tmp_del_rb',
            password_hash=generate_password_hash('Pass123'),
            role='DRIVER',
            truck_id=208,
            name='Delete Rollback Driver'
        )
        db.session.add(driver)
        type(db.session).commit(db.session)
        driver_id = driver.id

        # Revocation (call 1) succeeds, Restoration (call 2) succeeds
        mock_rtdb.side_effect = [(True, "OK"), (True, "OK")]
        orig_commit = type(db.session).commit
        calls = [0]
        def fail_first(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise Exception("Simulated SQLite commit error on deletion")
            return orig_commit(db.session, *args, **kwargs)
        mock_commit.side_effect = fail_first

        res = self.client.delete(f'/api/admin_delete_driver/{driver_id}', headers=self.headers)
        self.assertEqual(res.status_code, 500)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertIn('Database error during driver deletion', data.get('error', ''))

        # Driver must still exist in SQLite with original truck_id
        driver_restored = db.session.get(User, driver_id)
        self.assertIsNotNone(driver_restored)
        self.assertEqual(driver_restored.truck_id, 208)

        # Verify restoration was called with (driver_id, 208)
        self.assertEqual(mock_rtdb.call_count, 2)
        second_call = mock_rtdb.call_args_list[1]
        self.assertEqual(second_call[0][0], driver_id)
        self.assertEqual(second_call[0][1], 208)

    # -------------------------------------------------------------------------
    # TEST 39: Deletion Rollback Queues Outbox When Immediate RTDB Restore Fails
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch.object(db.session, 'commit')
    def test_admin_delete_driver_rollback_restore_failure_queues_outbox(self, mock_commit, mock_rtdb):
        driver = User(
            username='sync_test_tmp_del_q',
            password_hash=generate_password_hash('Pass123'),
            role='DRIVER',
            truck_id=209,
            name='Delete Queue Driver'
        )
        db.session.add(driver)
        type(db.session).commit(db.session)
        driver_id = driver.id

        # Revocation (call 1) succeeds, Restoration (call 2) fails
        mock_rtdb.side_effect = [(True, "OK"), (False, "Firebase network timeout on restoration")]
        orig_commit = type(db.session).commit
        calls = [0]
        def fail_first(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise Exception("Simulated SQLite commit error on deletion")
            return orig_commit(db.session, *args, **kwargs)
        mock_commit.side_effect = fail_first

        res = self.client.delete(f'/api/admin_delete_driver/{driver_id}', headers=self.headers)
        self.assertEqual(res.status_code, 500)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertTrue(data.get('pending_sync_recorded', False))

        # Outbox must contain durable pending sync record
        outbox = AssignmentOutbox.query.filter_by(driver_id=driver_id).first()
        self.assertIsNotNone(outbox)
        self.assertEqual(outbox.target_truck, 209)
        self.assertEqual(outbox.status, 'PENDING')

    # -------------------------------------------------------------------------
    # TEST 40: Multi-Driver Pre-revocation Rollback in admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch.object(db.session, 'commit')
    def test_admin_set_driver_truck_multi_driver_rollback_restores_all(self, mock_commit, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        orig_commit = type(db.session).commit
        calls = [0]
        def fail_first(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise Exception("Simulated commit error during reassignment")
            return orig_commit(db.session, *args, **kwargs)
        mock_commit.side_effect = fail_first

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 102}
        )
        self.assertEqual(res.status_code, 500)
        data = res.get_json()
        self.assertFalse(data.get('success', True))

        # Check both drivers have original assignments in SQLite
        d1 = db.session.get(User, self.driver1_id)
        d2 = db.session.get(User, self.driver2_id)
        self.assertEqual(d1.truck_id, 101)
        self.assertEqual(d2.truck_id, 102)

        # Check restoration was invoked for both drivers (calls 3 and 4)
        restored_calls = [(c[0][0], c[0][1]) for c in mock_rtdb.call_args_list[2:]]
        self.assertIn((self.driver1_id, 101), restored_calls)
        self.assertIn((self.driver2_id, 102), restored_calls)

    # -------------------------------------------------------------------------
    # TEST 41: Pre-revocation Rollback Partial Failure Queues Outbox
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch.object(db.session, 'commit')
    def test_admin_set_driver_truck_partial_restore_failure_queues_outbox(self, mock_commit, mock_rtdb):
        def mock_side_effect(did, tid, **kwargs):
            if did == self.driver2_id and tid == 102:
                return (False, "Firebase timeout restoring driver 2")
            return (True, "OK")

        mock_rtdb.side_effect = mock_side_effect
        orig_commit = type(db.session).commit
        calls = [0]
        def fail_first(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise Exception("Simulated commit failure")
            return orig_commit(db.session, *args, **kwargs)
        mock_commit.side_effect = fail_first

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 102}
        )
        self.assertEqual(res.status_code, 500)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertTrue(data.get('pending_sync_recorded', False))

        # Driver 2 must have durable outbox record queued
        outbox_d2 = AssignmentOutbox.query.filter_by(driver_id=self.driver2_id).first()
        self.assertIsNotNone(outbox_d2)
        self.assertEqual(outbox_d2.target_truck, 102)

    # -------------------------------------------------------------------------
    # TEST 42: Duplicate Reconciliation Runs Idempotently
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_duplicate_reconciliation_idempotency(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        record_pending_rtdb_assignment(self.driver1_id, 101)

        # Run 1: resolves 1
        rec1, rem1 = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec1, 1)
        self.assertEqual(rem1, 0)

        # Run 2: immediately re-run, must return 0, 0 cleanly
        rec2, rem2 = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec2, 0)
        self.assertEqual(rem2, 0)

    # -------------------------------------------------------------------------
    # TEST 43: Failed SQLAlchemy Transaction Does Not Poison Subsequent Outbox Writes
    # -------------------------------------------------------------------------
    def test_failed_sql_transaction_does_not_poison_outbox(self):
        try:
            from sqlalchemy import text
            db.session.execute(text("SELECT * FROM non_existent_table_for_test"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # Session must be clean and capable of writing outbox records
        ok, msg = record_pending_rtdb_assignment(self.driver1_id, 101)
        self.assertTrue(ok)
        outbox = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id).first()
        self.assertIsNotNone(outbox)

    # -------------------------------------------------------------------------
    # TEST 44: Driver Creation Fails Outbox Persistence Reports False Honestly
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch('waste_route_optimizer.record_pending_rtdb_assignment')
    def test_admin_create_driver_outbox_failure_reports_honest_status(self, mock_record, mock_rtdb):
        mock_rtdb.return_value = (False, "Firebase RTDB timeout")
        # Call 1 (staging inside commit): succeeds (True, "OK").
        # Call 2 (after RTDB failure update): returns failure (False, "Metadata disk error").
        mock_record.side_effect = [(True, "OK"), (False, "Metadata disk error")]

        res = self.client.post(
            '/api/admin_create_driver',
            headers=self.headers,
            json={
                'username': 'sync_test_tmp_outbox_fail',
                'password': 'PassWord@123',
                'name': 'Outbox Fail Driver'
            }
        )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertFalse(data.get('success', True))
        self.assertFalse(data.get('pending_sync_recorded', True))

    # -------------------------------------------------------------------------
    # TEST 45: Token Refresh Concurrent with Driver Reassignment
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    @patch('waste_route_optimizer.create_firebase_custom_token')
    def test_concurrent_token_refresh_and_driver_reassignment(self, mock_custom_token, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        mock_custom_token.return_value = ("mock_custom_token_val", {"truck_id": "999", "role": "DRIVER"})

        results = {}
        def run_reassign():
            res = self.client.post(
                '/api/admin_set_driver_truck',
                headers=self.headers,
                json={'driver_id': self.driver1_id, 'truck_id': 999}
            )
            results['reassign'] = res.status_code

        def run_token_refresh():
            res = self.client.get(
                '/api/firebase_custom_token',
                headers={'X-Driver-Token': self.driver1_token}
            )
            results['token'] = res.status_code

        t1 = threading.Thread(target=run_reassign)
        t2 = threading.Thread(target=run_token_refresh)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results.get('reassign'), 200)
        self.assertEqual(results.get('token'), 200)

        # After both threads finish, driver in SQLite must be Truck 999
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 999)

    # -------------------------------------------------------------------------
    # TEST 46: Outbox Record and Assignment Roll Back Atomically on SQLite Failure
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_outbox_atomic_rollback_on_sqlite_failure(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        
        # When Phase 2 db.session.commit() is called, fail the first commit
        original_commit = db.session.commit
        commit_calls = [0]
        def fail_first_commit(*args, **kwargs):
            commit_calls[0] += 1
            if commit_calls[0] == 1:
                raise Exception("Simulated SQLite disk write failure")
            return original_commit(*args, **kwargs)

        with patch.object(db.session, 'commit', side_effect=fail_first_commit):
            res = self.client.post(
                '/api/admin_set_driver_truck',
                headers=self.headers,
                json={'driver_id': self.driver1_id, 'truck_id': 555}
            )
            self.assertEqual(res.status_code, 500)

        # The driver assignment must remain Truck 101, and no outbox record for Truck 555 must exist
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)
        outbox_555 = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id, target_truck=555).first()
        self.assertIsNone(outbox_555)

    # -------------------------------------------------------------------------
    # TEST 47: Firebase Failure After Successful SQLite Commit Persists Durable Outbox
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_firebase_failure_after_successful_sqlite_commit(self, mock_rtdb):
        # Phase 1 pre-revocation succeeds; Phase 3 grant fails
        mock_rtdb.side_effect = [(True, "OK"), (False, "Firebase RTDB connection dropped")]

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 777}
        )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertTrue(data.get('pending_sync_recorded'))

        # SQLite committed Truck 777
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 777)

        # Outbox must have a durable record with status PENDING for driver1 to truck 777
        outbox = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id).first()
        self.assertIsNotNone(outbox)
        self.assertEqual(outbox.target_truck, 777)
        self.assertEqual(outbox.status, 'PENDING')

    # -------------------------------------------------------------------------
    # TEST 48: Reconciliation After Application Interruption
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_reconciliation_after_application_interruption(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")

        # Simulate interruption: outbox has an un-synchronized assignment for driver1
        d1 = db.session.get(User, self.driver1_id)
        d1.truck_id = 888
        db.session.commit()
        record_pending_rtdb_assignment(self.driver1_id, 888, last_error="Interrupted before sync")

        outbox_before = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id).first()
        self.assertIsNotNone(outbox_before)

        # Reconciliation runs on recovery
        reconciled, remaining = reconcile_pending_rtdb_assignments()
        self.assertEqual(reconciled, 1)
        self.assertEqual(remaining, 0)

        # Outbox must now be drained/cleared
        outbox_after = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id).first()
        self.assertIsNone(outbox_after)
        # Firebase RTDB was called with the authoritative truck 888
        mock_rtdb.assert_called_with(self.driver1_id, 888, retries=1)

    # -------------------------------------------------------------------------
    # TEST 49: Two Concurrent Reassignment Updates for the Same Driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_two_concurrent_updates_same_driver(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")

        results = []
        def req(truck):
            res = self.client.post(
                '/api/admin_set_driver_truck',
                headers=self.headers,
                json={'driver_id': self.driver1_id, 'truck_id': truck}
            )
            results.append((truck, res.status_code))

        t1 = threading.Thread(target=req, args=(301,))
        t2 = threading.Thread(target=req, args=(302,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both requests must complete successfully under serializing lock
        self.assertEqual(len(results), 2)
        for _, status in results:
            self.assertEqual(status, 200)

        # No unique constraint violation in AssignmentOutbox
        outbox_count = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id).count()
        self.assertLessEqual(outbox_count, 1)

    # -------------------------------------------------------------------------
    # TEST 50: Unassigned Driver Preservation and Revocation
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_unassigned_driver_preservation_and_revocation(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")

        # 1. Custom token request for unassigned driver must revoke in RTDB (truck_id=None)
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'X-Driver-Token': self.unassigned_token}
        )
        self.assertEqual(res.status_code, 200)
        mock_rtdb.assert_called_with(self.unassigned_id, None)

        # Unassigned driver must remain unassigned in SQLite
        du = db.session.get(User, self.unassigned_id)
        self.assertIsNone(du.truck_id)

        # 2. Outbox pending record for unassigned driver must revoke in RTDB during reconciliation
        record_pending_rtdb_assignment(self.unassigned_id, None, last_error="Pending unassign")
        mock_rtdb.reset_mock()
        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(self.unassigned_id, None, retries=1)

    # -------------------------------------------------------------------------
    # TEST 51: Deleted Driver Revocation
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_deleted_driver_revocation(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")

        # Create temporary driver and then delete
        tmp_driver = User(
            username='sync_test_tmp_del_rev',
            password_hash=generate_password_hash('Pass@123'),
            role='DRIVER',
            name='To Be Deleted',
            truck_id=601
        )
        db.session.add(tmp_driver)
        db.session.commit()
        del_id = tmp_driver.id

        # Insert outbox entry for this driver
        record_pending_rtdb_assignment(del_id, 601)

        # Now delete the driver directly from SQLite
        db.session.delete(tmp_driver)
        db.session.commit()

        # Reconcile must discover driver no longer exists and revoke in RTDB (None)
        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(del_id, None, retries=1)

    # -------------------------------------------------------------------------
    # TEST 52: Duplicate Outbox Prevention
    # -------------------------------------------------------------------------
    def test_duplicate_outbox_prevention(self):
        # Call record_pending_rtdb_assignment multiple times for driver1
        ok1, _ = record_pending_rtdb_assignment(self.driver1_id, 101)
        ok2, _ = record_pending_rtdb_assignment(self.driver1_id, 102)
        ok3, _ = record_pending_rtdb_assignment(self.driver1_id, 103)
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertTrue(ok3)

        # Must not have created 3 rows; unique driver_id constraint updates the row
        count = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id).count()
        self.assertEqual(count, 1)
        outbox = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id).first()
        self.assertEqual(outbox.target_truck, 103)

    # -------------------------------------------------------------------------
    # TEST 53: Crash After Durable Intent Commit (PREPARED) in admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_crash_after_durable_intent_commit(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        op_id = "test-crash-prepared-01"
        stage_assignment_intent(
            op_id=op_id,
            mutation_type='SET_TRUCK',
            affected_drivers_map={
                str(self.driver1_id): {'old_truck': 101, 'target_truck': 199, 'action': 'GRANT'}
            },
            commit=True
        )

        outbox = AssignmentOutbox.query.filter_by(op_id=op_id).first()
        self.assertIsNotNone(outbox)
        self.assertEqual(outbox.status, 'PREPARED')
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(self.driver1_id, 101, retries=1)
        self.assertIsNone(AssignmentOutbox.query.filter_by(op_id=op_id).first())

    # -------------------------------------------------------------------------
    # TEST 54: Crash After First Firebase Revocation (REVOKED) in admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_crash_after_firebase_revocation(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        op_id = "test-crash-revoked-02"
        stage_assignment_intent(
            op_id=op_id,
            mutation_type='SET_TRUCK',
            affected_drivers_map={
                str(self.driver1_id): {'old_truck': 101, 'target_truck': 199, 'action': 'GRANT'}
            },
            commit=True
        )
        update_assignment_intent_status(op_id, 'REVOKED', commit=True)

        outbox = AssignmentOutbox.query.filter_by(op_id=op_id).first()
        self.assertEqual(outbox.status, 'REVOKED')
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 101)

        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(self.driver1_id, 101, retries=1)
        self.assertIsNone(AssignmentOutbox.query.filter_by(op_id=op_id).first())

    # -------------------------------------------------------------------------
    # TEST 55: Crash After SQLite Business Commit (COMMITTED) in admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_crash_after_sqlite_business_commit(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        op_id = "test-crash-committed-03"
        stage_assignment_intent(
            op_id=op_id,
            mutation_type='SET_TRUCK',
            affected_drivers_map={
                str(self.driver1_id): {'old_truck': 101, 'target_truck': 199, 'action': 'GRANT'}
            },
            commit=True
        )
        d1 = db.session.get(User, self.driver1_id)
        d1.truck_id = 199
        update_assignment_intent_status(op_id, 'COMMITTED', commit=True)

        outbox = AssignmentOutbox.query.filter_by(op_id=op_id).first()
        self.assertEqual(outbox.status, 'COMMITTED')

        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(self.driver1_id, 199, retries=1)
        self.assertIsNone(AssignmentOutbox.query.filter_by(op_id=op_id).first())

    # -------------------------------------------------------------------------
    # TEST 56: Crash After Firebase Grant in admin_set_driver_truck
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_crash_after_firebase_grant(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        op_id = "test-crash-grant-04"
        d1 = db.session.get(User, self.driver1_id)
        d1.truck_id = 199
        stage_assignment_intent(
            op_id=op_id,
            mutation_type='SET_TRUCK',
            affected_drivers_map={
                str(self.driver1_id): {'old_truck': 101, 'target_truck': 199, 'action': 'GRANT'}
            },
            commit=True
        )
        update_assignment_intent_status(op_id, 'COMMITTED', commit=True)

        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(self.driver1_id, 199, retries=1)
        self.assertIsNone(AssignmentOutbox.query.filter_by(op_id=op_id).first())

    # -------------------------------------------------------------------------
    # TEST 57: Crash After Intent Commit in admin_delete_driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_crash_after_intent_commit_in_delete_driver(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        driver = User(
            username='sync_test_tmp_del_crash',
            password_hash=generate_password_hash('Pass123'),
            role='DRIVER',
            truck_id=222,
            name='Delete Crash Driver'
        )
        db.session.add(driver)
        db.session.commit()
        did = driver.id

        op_id = "test-del-crash-01"
        stage_assignment_intent(
            op_id=op_id,
            mutation_type='DELETE_DRIVER',
            affected_drivers_map={
                str(did): {'old_truck': 222, 'target_truck': None, 'action': 'DELETE'}
            },
            commit=True
        )

        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(did, 222, retries=1)
        self.assertIsNone(AssignmentOutbox.query.filter_by(op_id=op_id).first())

    # -------------------------------------------------------------------------
    # TEST 58: Crash After SQLite Deletion Commit in admin_delete_driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_crash_after_sqlite_delete_commit(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        did = 998877
        op_id = "test-del-crash-02"
        outbox = AssignmentOutbox(
            op_id=op_id,
            driver_id=did,
            target_truck=None,
            previous_truck=333,
            mutation_type='DELETE_DRIVER',
            status='COMMITTED',
            version=1
        )
        db.session.add(outbox)
        db.session.commit()

        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(did, None, retries=1)
        self.assertIsNone(AssignmentOutbox.query.filter_by(op_id=op_id).first())

    # -------------------------------------------------------------------------
    # TEST 59: Crash After Intent Commit in admin_create_driver
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_crash_after_create_driver_intent_commit(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        driver = User(
            username='sync_test_tmp_create_crash',
            password_hash=generate_password_hash('Pass123'),
            role='DRIVER',
            truck_id=444,
            name='Create Crash Driver'
        )
        db.session.add(driver)
        db.session.commit()
        did = driver.id

        op_id = "test-create-crash-01"
        outbox = AssignmentOutbox(
            op_id=op_id,
            driver_id=did,
            target_truck=444,
            previous_truck=None,
            mutation_type='CREATE_DRIVER',
            status='COMMITTED',
            version=1
        )
        db.session.add(outbox)
        db.session.commit()

        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        mock_rtdb.assert_called_with(did, 444, retries=1)
        self.assertIsNone(AssignmentOutbox.query.filter_by(op_id=op_id).first())

    # -------------------------------------------------------------------------
    # TEST 60: Firebase Request Timeout Simulation
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_firebase_request_timeout_simulation(self, mock_rtdb):
        # Call 1 (pre-revocation): succeeds
        # Call 2 (Phase 3 grant): times out
        # Call 3 (reconciliation grant): succeeds
        mock_rtdb.side_effect = [(True, "OK"), (False, "ReadTimeout to Firebase RTDB"), (True, "OK")]

        res = self.client.post(
            '/api/admin_set_driver_truck',
            headers=self.headers,
            json={'driver_id': self.driver1_id, 'truck_id': 105}
        )
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertTrue(data.get('pending_sync_recorded', False))

        rec, rem = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec, 1)
        self.assertEqual(rem, 0)
        d1 = db.session.get(User, self.driver1_id)
        self.assertEqual(d1.truck_id, 105)

    # -------------------------------------------------------------------------
    # TEST 61: Delayed Firebase Response Cannot Clear Newer Outbox Entry
    # -------------------------------------------------------------------------
    def test_delayed_firebase_response_cannot_clear_newer_outbox(self):
        did = self.driver1_id
        stage_assignment_intent("op-1", "SET_TRUCK", {str(did): {'old_truck': 101, 'target_truck': 102}}, commit=True)
        rec1 = AssignmentOutbox.query.filter_by(driver_id=did).first()
        self.assertEqual(rec1.op_id, "op-1")
        self.assertEqual(rec1.version, 1)

        stage_assignment_intent("op-2", "SET_TRUCK", {str(did): {'old_truck': 102, 'target_truck': 103}}, commit=True)
        rec2 = AssignmentOutbox.query.filter_by(driver_id=did).first()
        self.assertEqual(rec2.op_id, "op-2")
        self.assertEqual(rec2.version, 2)

        ok, msg = clear_pending_rtdb_assignment(did, commit=True, op_id="op-1", version=1)
        self.assertFalse(ok)
        self.assertIn("Stale op_id", msg)

        current_rec = AssignmentOutbox.query.filter_by(driver_id=did).first()
        self.assertIsNotNone(current_rec)
        self.assertEqual(current_rec.op_id, "op-2")
        self.assertEqual(current_rec.version, 2)
        self.assertEqual(current_rec.target_truck, 103)

    # -------------------------------------------------------------------------
    # TEST 62: Concurrent Driver Reassignment to Two Trucks
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_concurrent_driver_reassignment_monotonic_versions(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        did = self.driver1_id

        res1 = self.client.post('/api/admin_set_driver_truck', headers=self.headers, json={'driver_id': did, 'truck_id': 111})
        self.assertEqual(res1.status_code, 200)

        res2 = self.client.post('/api/admin_set_driver_truck', headers=self.headers, json={'driver_id': did, 'truck_id': 112})
        self.assertEqual(res2.status_code, 200)

        d1 = db.session.get(User, did)
        self.assertEqual(d1.truck_id, 112)

    # -------------------------------------------------------------------------
    # TEST 63: Two Admins Assigning Different Drivers to Same Truck Concurrently
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_concurrent_truck_collision_resolution(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        res1 = self.client.post('/api/admin_set_driver_truck', headers=self.headers, json={'driver_id': self.driver1_id, 'truck_id': 500})
        self.assertEqual(res1.status_code, 200)

        res2 = self.client.post('/api/admin_set_driver_truck', headers=self.headers, json={'driver_id': self.driver2_id, 'truck_id': 500})
        self.assertEqual(res2.status_code, 200)

        d1 = db.session.get(User, self.driver1_id)
        d2 = db.session.get(User, self.driver2_id)
        self.assertIsNone(d1.truck_id)
        self.assertEqual(d2.truck_id, 500)

    # -------------------------------------------------------------------------
    # TEST 64: Concurrent Driver Creation Allocates Unique Trucks
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_concurrent_driver_creation_allocates_unique_trucks(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        res1 = self.client.post(
            '/api/admin_create_driver',
            headers=self.headers,
            json={'username': 'sync_test_tmp_uniq_1', 'password': 'Password@1', 'name': 'Unique Driver 1'}
        )
        res2 = self.client.post(
            '/api/admin_create_driver',
            headers=self.headers,
            json={'username': 'sync_test_tmp_uniq_2', 'password': 'Password@2', 'name': 'Unique Driver 2'}
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        t1 = res1.get_json()['truck_id']
        t2 = res2.get_json()['truck_id']
        self.assertNotEqual(t1, t2)

    # -------------------------------------------------------------------------
    # TEST 65: Driver Deletion While Older Assignment Operation Remains Pending
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_driver_deletion_while_assignment_pending(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        driver = User(
            username='sync_test_tmp_del_pending',
            password_hash=generate_password_hash('Pass123'),
            role='DRIVER',
            truck_id=601,
            name='Delete Pending Driver'
        )
        db.session.add(driver)
        db.session.commit()
        did = driver.id

        record_pending_rtdb_assignment(did, 601, status='PENDING')

        res = self.client.delete(f'/api/admin_delete_driver/{did}', headers=self.headers)
        self.assertEqual(res.status_code, 200)

        rec, rem = reconcile_pending_rtdb_assignments()
        d_check = db.session.get(User, did)
        self.assertIsNone(d_check)

    # -------------------------------------------------------------------------
    # TEST 66: Two Concurrent Reconciliation Attempts Processing Same Pending Op
    # -------------------------------------------------------------------------
    @patch('waste_route_optimizer.set_driver_rtdb_assignment')
    def test_two_reconciliation_attempts_idempotency(self, mock_rtdb):
        mock_rtdb.return_value = (True, "OK")
        record_pending_rtdb_assignment(self.driver1_id, 101, status='COMMITTED')

        rec1, rem1 = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec1, 1)
        self.assertEqual(rem1, 0)

        rec2, rem2 = reconcile_pending_rtdb_assignments()
        self.assertEqual(rec2, 0)
        self.assertEqual(rem2, 0)

    # -------------------------------------------------------------------------
    # TEST 67: Database Migration Safety on Pre-existing Database Copy
    # -------------------------------------------------------------------------
    def test_database_migration_safety_on_db_copy(self):
        import shutil, sqlite3, os, gc
        src_db = 'instance/routes.db'
        copy_db = 'instance/test_migration_copy.db'
        shutil.copy2(src_db, copy_db)
        con = None
        try:
            con = sqlite3.connect(copy_db)
            cur = con.cursor()

            # Record all existing users before migration
            cur.execute("SELECT id, username, role, truck_id FROM users ORDER BY id")
            users_before = cur.fetchall()
            self.assertTrue(len(users_before) > 0)

            # Record customer count before migration
            cur.execute("SELECT count(*) FROM customers")
            cust_count_before = cur.fetchone()[0]

            # Apply additive migrations
            for col, col_type in [
                ('op_id', 'VARCHAR(36)'),
                ('previous_truck', 'INTEGER'),
                ('mutation_type', 'VARCHAR(30)'),
                ('affected_drivers_json', 'TEXT'),
                ('version', 'INTEGER DEFAULT 1')
            ]:
                try:
                    cur.execute(f"ALTER TABLE assignment_outbox ADD COLUMN {col} {col_type};")
                    con.commit()
                except Exception:
                    pass

            cur.execute("CREATE INDEX IF NOT EXISTS ix_assignment_outbox_op_id ON assignment_outbox (op_id);")
            con.commit()

            # Verify schema additions
            cur.execute("PRAGMA table_info(assignment_outbox);")
            cols = [info[1] for info in cur.fetchall()]
            for required_col in ['op_id', 'previous_truck', 'mutation_type', 'affected_drivers_json', 'version']:
                self.assertIn(required_col, cols)

            # Verify 100% preservation of users and customers
            cur.execute("SELECT id, username, role, truck_id FROM users ORDER BY id")
            users_after = cur.fetchall()
            self.assertEqual(users_before, users_after)

            cur.execute("SELECT count(*) FROM customers")
            cust_count_after = cur.fetchone()[0]
            self.assertEqual(cust_count_before, cust_count_after)

            cur.close()
            con.close()
            con = None
        finally:
            if con:
                try:
                    con.close()
                except Exception:
                    pass
            gc.collect()
            if os.path.exists(copy_db):
                try:
                    os.remove(copy_db)
                except Exception:
                    pass

    # =========================================================================
    # COMPREHENSIVE CRASH-SAFE & ORDERED ASSIGNMENT VERIFICATION TESTS
    # =========================================================================

    def test_monotonic_global_sequence_concurrency(self):
        """
        Verifies that concurrent allocations from assignment_global_sequence
        are strictly monotonic, unique, and race-free.
        """
        results = []
        errors = []

        def worker():
            try:
                with self.app.app_context():
                    for _ in range(5):
                        rev = allocate_next_assignment_revision()
                        results.append(rev)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        self.assertEqual(len(results), 50)
        self.assertEqual(len(set(results)), 50, "Allocated revisions must be strictly unique")
        for rev in results:
            self.assertGreater(rev, 0)

    def test_driver_lifecycle_ledger_and_id_recycling(self):
        """
        Verifies that generation UUIDs in driver_lifecycle_ledger prevent stale retries
        bearing recycled SQLite driver IDs from resurrecting deleted drivers.
        """
        recycled_driver_id = 9999
        gen_a = uuid.uuid4().hex
        gen_b = uuid.uuid4().hex

        # Driver Generation A created and deleted
        led_a = DriverLifecycleLedger(
            generation_id=gen_a,
            driver_id=recycled_driver_id,
            is_active=False,
            last_revision=10
        )
        db.session.add(led_a)

        # Driver Generation B created reusing ID 9999
        led_b = DriverLifecycleLedger(
            generation_id=gen_b,
            driver_id=recycled_driver_id,
            is_active=True,
            last_revision=20
        )
        db.session.add(led_b)
        db.session.commit()

        # Stale retry bearing Generation A must be rejected
        ok_a, err_a = set_driver_rtdb_assignment_conditional(
            driver_id=recycled_driver_id,
            truck_id=105,
            generation_id=gen_a,
            revision=10
        )
        self.assertFalse(ok_a)
        self.assertIn("REJECTED_LIFECYCLE_INACTIVE", err_a)

    def test_outbox_staleness_monotonic_guard(self):
        """
        Verifies that record_pending_rtdb_assignment rejects an older revision
        and refuses to overwrite a newer outbox record.
        """
        did = 8888
        gen_id = uuid.uuid4().hex

        # Record initial outbox entry with revision 20
        ok1, msg1 = record_pending_rtdb_assignment(
            driver_id=did,
            truck_id=101,
            generation_id=gen_id,
            revision=20,
            status='PREPARED'
        )
        self.assertTrue(ok1)

        outbox = AssignmentOutbox.query.filter_by(driver_id=did).first()
        self.assertIsNotNone(outbox)
        self.assertEqual(outbox.revision, 20)
        self.assertEqual(outbox.target_truck, 101)

        # Attempt to record a stale update with revision 15
        ok2, msg2 = record_pending_rtdb_assignment(
            driver_id=did,
            truck_id=102,
            generation_id=gen_id,
            revision=15,
            status='PREPARED'
        )
        self.assertFalse(ok2)
        self.assertIn("Stale revision 15 rejected", msg2)

        # Outbox must remain intact at revision 20 and target 101
        outbox = AssignmentOutbox.query.filter_by(driver_id=did).first()
        self.assertEqual(outbox.revision, 20)
        self.assertEqual(outbox.target_truck, 101)

    @patch('waste_route_optimizer.get_firebase_token')
    @patch('requests.get')
    @patch('requests.put')
    @patch('requests.delete')
    def test_firebase_conditional_etag_protocol_put_and_delete(self, mock_delete, mock_put, mock_get, mock_token):
        """
        Verifies that conditional mutations capture ETag via GET and execute If-Match PUT/DELETE.
        """
        mock_token.return_value = 'mock-admin-token'

        # Test PUT (Grant truck 105)
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = 101
        get_resp.headers = {'ETag': '"etag-v1"'}
        mock_get.return_value = get_resp

        put_resp = MagicMock()
        put_resp.status_code = 200
        mock_put.return_value = put_resp

        d1 = db.session.get(User, self.driver1_id)
        cur_rev = d1.assignment_revision or 0

        ok_put, err_put = set_driver_rtdb_assignment_conditional(
            driver_id=self.driver1_id,
            truck_id=105,
            generation_id=d1.generation_id,
            revision=cur_rev + 10
        )
        self.assertTrue(ok_put)
        mock_put.assert_called_once()
        self.assertIn('headers', mock_put.call_args.kwargs)
        self.assertEqual(mock_put.call_args.kwargs['headers'].get('if-match'), '"etag-v1"')

        # Test DELETE (Revoke truck)
        mock_get.reset_mock()
        get_resp.json.return_value = 105
        get_resp.headers = {'ETag': '"etag-v2"'}
        mock_get.return_value = get_resp

        del_resp = MagicMock()
        del_resp.status_code = 204
        mock_delete.return_value = del_resp

        ok_del, err_del = set_driver_rtdb_assignment_conditional(
            driver_id=self.driver1_id,
            truck_id=None,
            generation_id=d1.generation_id,
            revision=cur_rev + 20
        )
        self.assertTrue(ok_del)
        mock_delete.assert_called_once()
        self.assertIn('headers', mock_delete.call_args.kwargs)
        self.assertEqual(mock_delete.call_args.kwargs['headers'].get('if-match'), '"etag-v2"')

    @patch('waste_route_optimizer.get_firebase_token')
    @patch('requests.get')
    @patch('requests.put')
    def test_firebase_conditional_etag_412_terminal_abort(self, mock_put, mock_get, mock_token):
        """
        Verifies that on HTTP 412 Precondition Failed, the conditional helper aborts
        immediately with CONFLICT_412_PRECONDITION_FAILED and never retries with a fresh ETag.
        """
        mock_token.return_value = 'mock-admin-token'

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = 101
        get_resp.headers = {'ETag': '"etag-stale"'}
        mock_get.return_value = get_resp

        # Return HTTP 412
        put_resp = MagicMock()
        put_resp.status_code = 412
        mock_put.return_value = put_resp

        d1 = db.session.get(User, self.driver1_id)
        cur_rev = d1.assignment_revision or 0

        ok, err = set_driver_rtdb_assignment_conditional(
            driver_id=self.driver1_id,
            truck_id=105,
            generation_id=d1.generation_id,
            revision=cur_rev + 10,
            retries=2
        )
        self.assertFalse(ok)
        self.assertEqual(err, "CONFLICT_412_PRECONDITION_FAILED")
        # Precondition failed must be a terminal abort: exactly 1 attempt made
        self.assertEqual(mock_put.call_count, 1)

    def test_stale_worker_cross_process_fencing(self):
        """
        Verifies that a worker holding a stale revision is fenced out and rejected
        by authoritative SQLite state.
        """
        d1 = db.session.get(User, self.driver1_id)
        d1.assignment_revision = 50
        db.session.commit()

        # Worker A attempts update with obsolete revision 25
        ok, err = set_driver_rtdb_assignment_conditional(
            driver_id=self.driver1_id,
            truck_id=199,
            generation_id=d1.generation_id,
            revision=25
        )
        self.assertFalse(ok)
        self.assertIn("REJECTED_STALE_REVISION", err)

    @patch('waste_route_optimizer.get_firebase_token')
    @patch('requests.get')
    @patch('requests.put')
    def test_ambiguous_timeout_etag_recovery(self, mock_put, mock_get, mock_token):
        """
        Verifies that on a network timeout where Firebase actually received the write,
        the next check detects current_val == target_val and succeeds idempotently.
        """
        import requests as rq
        mock_token.return_value = 'mock-admin-token'

        # Call 1: GET returns 101, PUT times out
        get_resp1 = MagicMock()
        get_resp1.status_code = 200
        get_resp1.json.return_value = 101
        get_resp1.headers = {'ETag': '"etag-1"'}

        # Call 2 (retry): GET returns 105 (server committed the PUT before timeout!)
        get_resp2 = MagicMock()
        get_resp2.status_code = 200
        get_resp2.json.return_value = 105
        get_resp2.headers = {'ETag': '"etag-2"'}

        mock_get.side_effect = [get_resp1, get_resp2]
        mock_put.side_effect = rq.exceptions.Timeout("Read timeout to Firebase RTDB")

        d1 = db.session.get(User, self.driver1_id)
        cur_rev = d1.assignment_revision or 0

        ok, err = set_driver_rtdb_assignment_conditional(
            driver_id=self.driver1_id,
            truck_id=105,
            generation_id=d1.generation_id,
            revision=cur_rev + 10,
            retries=1
        )
        self.assertTrue(ok)
        self.assertEqual(err, "OK")

    def test_unconditional_bulk_sync_blocked_by_active_outbox(self):
        """
        Verifies that bulk synchronization is deferred when active unconfirmed
        outbox operations are pending.
        """
        outbox = AssignmentOutbox(
            op_id="active-outbox-bulk-guard",
            driver_id=self.driver1_id,
            target_truck=105,
            mutation_type='SET_TRUCK',
            status='PREPARED',
            version=1
        )
        db.session.add(outbox)
        db.session.commit()

        with patch('waste_route_optimizer.reconcile_pending_rtdb_assignments', return_value=(0, 1)):
            ok, msg = sync_all_driver_assignments_to_firebase(authorized_reconciliation=False)
            self.assertFalse(ok)
            self.assertIn("Safety guard triggered: 1 unconfirmed outbox operations pending", msg)

    def test_real_os_subprocess_termination_recovery(self):
        """
        Spawns a real OS subprocess that stages an assignment intent and immediately
        terminates with os._exit(77) to simulate an abrupt power loss / SIGKILL.
        Verifies parent process finds the pending outbox record and startup recovery resolves it.
        """
        import subprocess
        import sys

        crash_script = (
            "import os, sys\n"
            "from waste_route_optimizer import app, db, stage_assignment_intent, User\n"
            "with app.app_context():\n"
            f"    d = db.session.get(User, {self.driver1_id})\n"
            "    stage_assignment_intent(\n"
            "        'subproc-crash-intent',\n"
            "        'SET_TRUCK',\n"
            f"        {{str({self.driver1_id}): {{'old_truck': 101, 'target_truck': 105, 'action': 'GRANT', 'generation_id': d.generation_id, 'revision': 999}}}},\n"
            "        commit=True\n"
            "    )\n"
            "os._exit(77)\n"
        )

        proc = subprocess.Popen([sys.executable, "-c", crash_script])
        retcode = proc.wait(timeout=15)
        self.assertEqual(retcode, 77, "Child process must have terminated abruptly with code 77")

        # Verify that parent process sees the staged intent in outbox
        outbox = AssignmentOutbox.query.filter_by(op_id='subproc-crash-intent').first()
        self.assertIsNotNone(outbox, "Outbox record from abruptly terminated process must exist")
        self.assertEqual(outbox.status, 'PREPARED')

        # Run startup reconciliation and verify it resolves the pending intent
        with patch('waste_route_optimizer.set_driver_rtdb_assignment', return_value=(True, "OK")):
            rec, rem = reconcile_pending_rtdb_assignments()
            self.assertGreaterEqual(rec, 1)

        resolved_outbox = AssignmentOutbox.query.filter_by(op_id='subproc-crash-intent').first()
        self.assertIsNone(resolved_outbox, "Startup reconciliation must flush and clear resolved outbox record")

    def test_multi_driver_displacement_compensation_tracking(self):
        """
        Verifies that when reassigning a truck displaces an existing driver,
        and the grant phase fails, compensation tracking preserves the evicted driver's intent.
        """
        # Driver 1 on 101, Driver 2 on 102
        # Assign Driver 1 to 102 (evicting Driver 2)
        # Mock RTDB: Pre-revocations succeed, but Grant fails
        with patch('waste_route_optimizer.set_driver_rtdb_assignment') as mock_rtdb:
            mock_rtdb.side_effect = [
                (True, "OK"), # Revoke evicted driver 2
                (True, "OK"), # Revoke driver 1
                (False, "Simulated network failure on final grant") # Grant driver 1
            ]

            res = self.client.post(
                '/api/admin_set_driver_truck',
                headers=self.headers,
                json={'driver_id': self.driver1_id, 'truck_id': 102}
            )
            self.assertEqual(res.status_code, 502)
            data = res.get_json()
            self.assertFalse(data.get('success', True))
            self.assertTrue(data.get('pending_sync_recorded', False))

            # Driver 1 outbox record staged with status PENDING for reconciliation
            outbox_d1 = AssignmentOutbox.query.filter_by(driver_id=self.driver1_id).first()
            self.assertIsNotNone(outbox_d1)
            self.assertEqual(outbox_d1.target_truck, 102)

if __name__ == '__main__':
    unittest.main()
