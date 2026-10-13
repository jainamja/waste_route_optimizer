import unittest
import json
from unittest.mock import patch, MagicMock

# Import app and models
import waste_route_optimizer as w
from waste_route_optimizer import app, db, User, Customer, SavedTemplate, Metadata

class TestSavedTemplateIsolation(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        
        # Authenticate admin
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'ADMIN'
            sess['_fresh'] = True

    def tearDown(self):
        self.ctx.pop()

    @patch('waste_route_optimizer.requests.put')
    @patch('waste_route_optimizer.requests.delete')
    @patch('waste_route_optimizer.requests.get')
    @patch('waste_route_optimizer.requests.post')
    def test_saved_template_isolation_lifecycle(self, mock_post, mock_get, mock_delete, mock_put):
        # FIREBASE SAFETY: Mock all network calls
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {'idToken': 'mock_token'})
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {})
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {'name': 'ok'})
        mock_delete.return_value = MagicMock(status_code=200, json=lambda: {'name': 'ok'})

        # Clean existing test data
        Customer.query.filter(Customer.truck_id.in_([10, 11])).delete()
        SavedTemplate.query.filter(SavedTemplate.name.like('IsolationTest_%')).delete()
        db.session.commit()

        # Step 1: Create a Master Template in Library
        stops_data = [
            {'id': 9001, 'name': 'Stop Alpha', 'lat': 28.5, 'lng': 77.2, 'truck_id': 10, 'stop_number': 1, 'status': 'PENDING'},
            {'id': 9002, 'name': 'Stop Beta', 'lat': 28.6, 'lng': 77.3, 'truck_id': 10, 'stop_number': 2, 'status': 'PENDING'},
            {'id': 9003, 'name': 'Stop Gamma', 'lat': 28.7, 'lng': 77.4, 'truck_id': 10, 'stop_number': 3, 'status': 'PENDING'},
        ]
        master_tmpl = SavedTemplate(
            name='IsolationTest_Master_Route',
            metadata_json=json.dumps({'workspace_truck_ids': '[10]'}),
            customers_json=json.dumps(stops_data),
            is_assigned_instance=False
        )
        db.session.add(master_tmpl)
        db.session.commit()
        master_id = master_tmpl.id

        # Verify it appears in library
        res = self.client.get('/api/templates')
        data = res.get_json()
        tmpl_ids = [t['id'] for t in data['templates']]
        self.assertIn(master_id, tmpl_ids)

        # Step 2: Assign Master Template to Driver 10
        driver = User.query.filter_by(role='DRIVER', username='driver10').first()
        if not driver:
            driver = User(username='driver10', role='DRIVER', truck_id=10)
            db.session.add(driver)
            db.session.commit()
        driver.truck_id = 10

        res = self.client.post('/api/assign_route', json={
            'driver_id': driver.id,
            'template_id': master_id,
            'truck_id': 10
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        # Refresh driver
        db.session.refresh(driver)
        assigned_id = driver.assigned_template_id
        self.assertIsNotNone(assigned_id)
        # CRITICAL ASSERTION: Assigned template ID must be decoupled from master template ID!
        self.assertNotEqual(assigned_id, master_id, "Driver assigned template ID MUST NOT point to the master template!")

        assigned_tmpl = SavedTemplate.query.get(assigned_id)
        self.assertIsNotNone(assigned_tmpl)
        self.assertTrue(assigned_tmpl.is_assigned_instance, "Assigned instance must have is_assigned_instance=True")

        # Verify Driver 10 has customers in DB
        custs = Customer.query.filter_by(truck_id=10).order_by(Customer.stop_number.asc()).all()
        self.assertEqual(len(custs), 3)

        # Driver completes Stop Alpha
        stop_alpha = Customer.query.filter_by(truck_id=10, stop_number=1).first()
        stop_alpha.status = 'COMPLETED'
        db.session.commit()

        # Step 3: Admin opens Master Template in Route Dashboard for editing (mode=edit)
        res = self.client.post(f'/api/deploy_template/{master_id}?mode=edit')
        self.assertEqual(res.status_code, 200)
        
        # Verify Driver 10's active route was NOT touched by opening the master template for edit
        db.session.refresh(stop_alpha)
        self.assertEqual(stop_alpha.status, 'COMPLETED', "Active driver stop must remain COMPLETED when master is opened for edit!")
        custs_after_edit_open = Customer.query.filter_by(truck_id=10).all()
        self.assertEqual(len(custs_after_edit_open), 3, "Active driver stops must not be deleted when master is opened for edit!")

        # Step 4: Admin edits the stops on Route Dashboard and saves the Master Template
        # In Route Dashboard, master stops are updated in workspace (e.g. Stop Gamma changed to Stop Delta)
        new_master_stops = [
            {'id': 9001, 'name': 'Stop Alpha', 'lat': 28.5, 'lng': 77.2, 'truck_id': 10, 'stop_number': 1, 'status': 'PENDING'},
            {'id': 9002, 'name': 'Stop Beta', 'lat': 28.6, 'lng': 77.3, 'truck_id': 10, 'stop_number': 2, 'status': 'PENDING'},
            {'id': 9004, 'name': 'Stop Delta_NEW', 'lat': 28.8, 'lng': 77.5, 'truck_id': 10, 'stop_number': 3, 'status': 'PENDING'},
        ]
        # Workspace metadata reflects workspace trucks
        ws_meta = Metadata.query.filter_by(key='workspace_truck_ids').first()
        if not ws_meta:
            ws_meta = Metadata(key='workspace_truck_ids', value='[10]')
            db.session.add(ws_meta)
        else:
            ws_meta.value = '[10]'
        db.session.commit()

        # Save the master template
        res = self.client.post('/api/save_template', json={
            'id': master_id,
            'name': 'IsolationTest_Master_Route_Updated',
            'is_edit_assigned': False
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        # Verify Master Template was updated in library
        db.session.refresh(master_tmpl)
        self.assertEqual(master_tmpl.name, 'IsolationTest_Master_Route_Updated')

        # CRITICAL ASSERTION: Driver 10's active route is COMPLETELY UNAFFECTED!
        db.session.refresh(stop_alpha)
        self.assertEqual(stop_alpha.status, 'COMPLETED', "Driver's active route must NOT be reset to PENDING when master template is saved!")
        custs_driver = Customer.query.filter_by(truck_id=10).order_by(Customer.stop_number.asc()).all()
        self.assertEqual(len(custs_driver), 3)
        self.assertEqual(custs_driver[0].status, 'COMPLETED')
        self.assertEqual(custs_driver[1].name, 'Stop Beta')
        self.assertEqual(custs_driver[2].name, 'Stop Gamma', "Driver's stops must retain their existing stops (Stop Gamma), not be replaced by Stop Delta_NEW!")

        # Step 5: Check GET /api/templates does NOT show the assigned instance
        res = self.client.get('/api/templates')
        tmpl_list = res.get_json()['templates']
        tmpl_ids = [t['id'] for t in tmpl_list]
        self.assertIn(master_id, tmpl_ids)
        self.assertNotIn(assigned_id, tmpl_ids, "Assigned instance must NOT appear in Saved Templates library!")

        # Step 6: Check GET /api/assigned_routes
        res = self.client.get('/api/assigned_routes')
        assigned_routes = res.get_json()['assigned_routes']
        driver10_route = next((r for r in assigned_routes if r['truck_id'] == 10), None)
        self.assertIsNotNone(driver10_route)
        self.assertEqual(driver10_route['id'], assigned_id)
        self.assertEqual(driver10_route['stops_count'], 3)
        self.assertEqual(driver10_route['pending_stops_count'], 2)  # 1 completed, 2 pending

        # Step 7: Admin edits Driver 10's Assigned Route (mode=edit_assigned)
        res = self.client.post('/api/save_template', json={
            'id': assigned_id,
            'name': 'IsolationTest_Driver10_Assigned_Modified',
            'is_edit_assigned': True
        })
        self.assertEqual(res.status_code, 200)

        # Verify master template was NOT modified by saving assigned route
        db.session.refresh(master_tmpl)
        self.assertEqual(master_tmpl.name, 'IsolationTest_Master_Route_Updated')

        # Step 8: Unassign Driver 10
        res = self.client.post('/api/unassign_route', json={
            'template_id': assigned_id,
            'truck_id': 10
        })
        self.assertEqual(res.status_code, 200)

        # Verify driver assignment is None
        db.session.refresh(driver)
        self.assertIsNone(driver.assigned_template_id)

        # Verify assigned instance was cleaned up
        cleaned_inst = SavedTemplate.query.get(assigned_id)
        self.assertIsNone(cleaned_inst, "Assigned instance SavedTemplate row must be cleaned up on unassign!")

        # Verify master template still exists in library
        self.assertIsNotNone(SavedTemplate.query.get(master_id), "Master template in library must not be deleted!")

        # Cleanup
        db.session.delete(master_tmpl)
        Customer.query.filter_by(truck_id=10).delete()
        db.session.commit()
        print("\nTest 1 (assign_route isolation): PASSED")

    @patch('waste_route_optimizer.requests.put')
    @patch('waste_route_optimizer.requests.delete')
    @patch('waste_route_optimizer.requests.get')
    @patch('waste_route_optimizer.requests.post')
    def test_assign_driver_isolation(self, mock_post, mock_get, mock_delete, mock_put):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {'idToken': 'mock_token'})
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {})
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {'name': 'ok'})
        mock_delete.return_value = MagicMock(status_code=200, json=lambda: {'name': 'ok'})

        # Clean existing test data
        Customer.query.filter(Customer.truck_id == 11).delete()
        SavedTemplate.query.filter(SavedTemplate.name.like('IsolationTest2_%')).delete()
        db.session.commit()

        # Step 1: Create a Master Template
        stops_data = [
            {'id': 9101, 'name': 'Stop 1', 'lat': 28.5, 'lng': 77.2, 'truck_id': 11, 'stop_number': 1, 'status': 'PENDING'},
            {'id': 9102, 'name': 'Stop 2', 'lat': 28.6, 'lng': 77.3, 'truck_id': 11, 'stop_number': 2, 'status': 'PENDING'},
        ]
        master_tmpl = SavedTemplate(
            name='IsolationTest2_Master',
            metadata_json=json.dumps({'workspace_truck_ids': '[11]'}),
            customers_json=json.dumps(stops_data),
            is_assigned_instance=False
        )
        db.session.add(master_tmpl)
        db.session.commit()
        master_id = master_tmpl.id

        # Insert stops for Truck 11
        for s in stops_data:
            db.session.add(Customer(id=s['id'], name=s['name'], lat=s['lat'], lng=s['lng'], truck_id=11, stop_number=s['stop_number'], status='PENDING'))
        db.session.commit()

        # Set workspace metadata current_template_id to master_id
        curr_id = Metadata.query.filter_by(key='current_template_id').first()
        if not curr_id:
            curr_id = Metadata(key='current_template_id', value=str(master_id))
            db.session.add(curr_id)
        else:
            curr_id.value = str(master_id)
        db.session.commit()

        driver = User.query.filter_by(role='DRIVER', username='driver9').first()
        if not driver:
            driver = User(username='driver9', role='DRIVER', truck_id=None)
            db.session.add(driver)
            db.session.commit()

        # Assign driver via /api/assign_driver
        res = self.client.post('/api/assign_driver', json={
            'driver_id': driver.id,
            'truck_id': 11
        })
        self.assertEqual(res.status_code, 200)

        db.session.refresh(driver)
        self.assertIsNotNone(driver.assigned_template_id)
        # CRITICAL ASSERTION: Driver assigned template ID must be decoupled from master template ID!
        self.assertNotEqual(driver.assigned_template_id, master_id, "assign_driver MUST NOT link directly to master template ID!")
        
        assigned_inst = SavedTemplate.query.get(driver.assigned_template_id)
        self.assertTrue(assigned_inst.is_assigned_instance)

        # Admin saves master template
        res = self.client.post('/api/save_template', json={
            'id': master_id,
            'name': 'IsolationTest2_Master_Renamed',
            'is_edit_assigned': False
        })
        self.assertEqual(res.status_code, 200)

        # Driver's stops are untouched
        custs = Customer.query.filter_by(truck_id=11).all()
        self.assertEqual(len(custs), 2)

        # Cleanup
        db.session.delete(assigned_inst)
        db.session.delete(master_tmpl)
        Customer.query.filter_by(truck_id=11).delete()
        driver.assigned_template_id = None
        driver.truck_id = None
        db.session.commit()
        print("Test 2 (assign_driver isolation): PASSED")

if __name__ == '__main__':
    unittest.main()
