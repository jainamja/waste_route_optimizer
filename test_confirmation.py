import unittest
import json
from waste_route_optimizer import app, db, User, Customer
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

class ConfirmationTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app.test_client()
        with app.app_context():
            db.create_all()
            
            admin = User(username='admin_test', role='ADMIN', password_hash=generate_password_hash('admin'))
            driver = User(username='driver_test', role='DRIVER', truck_id=None, password_hash=generate_password_hash('driver'))
            db.session.add(admin)
            db.session.add(driver)
            
            c1 = Customer(id=1, name='Cust 1', truck_id=1, confirmation='NOT_CONFIRMED')
            c2 = Customer(id=2, name='Cust 2', truck_id=1, confirmation='NOT_CONFIRMED')
            depot = Customer(id=-1001, name='End Location / Depot', truck_id=1)
            db.session.add_all([c1, c2, depot])
            db.session.commit()
            
            self.admin_id = admin.id
            self.driver_id = driver.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self):
        return self.app.post('/login', data=dict(
            username='admin_test',
            password='admin'
        ), follow_redirects=True)

    @patch('requests.post')
    @patch('requests.patch')
    def test_assign_driver_with_confirmations(self, mock_patch, mock_post):
        self.login()
        
        mock_auth_res = MagicMock()
        mock_auth_res.status_code = 200
        mock_auth_res.json.return_value = {'idToken': 'mock_token'}
        mock_post.return_value = mock_auth_res
        
        mock_patch_res = MagicMock()
        mock_patch_res.status_code = 200
        mock_patch.return_value = mock_patch_res
        
        res = self.app.post('/api/assign_driver', json={
            'driver_id': self.driver_id,
            'truck_id': 1,
            'confirmations': {
                '1': 'CONFIRMED'
            }
        })
        
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertTrue(data['firebase_synced'])
        
        with app.app_context():
            c1 = Customer.query.get(1)
            self.assertEqual(c1.confirmation, 'CONFIRMED')
            
            c2 = Customer.query.get(2)
            self.assertEqual(c2.confirmation, 'NOT_CONFIRMED')
            
            driver = User.query.get(self.driver_id)
            self.assertEqual(driver.truck_id, 1)

    @patch('requests.post')
    @patch('requests.patch')
    def test_assign_driver_invalid_value(self, mock_patch, mock_post):
        self.login()
        
        mock_auth_res = MagicMock()
        mock_auth_res.status_code = 200
        mock_auth_res.json.return_value = {'idToken': 'mock_token'}
        mock_post.return_value = mock_auth_res
        
        res = self.app.post('/api/assign_driver', json={
            'driver_id': self.driver_id,
            'truck_id': 1,
            'confirmations': {
                '1': 'YES_PLEASE_SURE'
            }
        })
        
        self.assertEqual(res.status_code, 200)
        
        with app.app_context():
            c1 = Customer.query.get(1)
            self.assertEqual(c1.confirmation, 'NOT_CONFIRMED')

    def test_assign_driver_no_confirmations(self):
        self.login()
        res = self.app.post('/api/assign_driver', json={
            'driver_id': self.driver_id,
            'truck_id': 1
        })
        
        self.assertEqual(res.status_code, 200)
        with app.app_context():
            c1 = Customer.query.get(1)
            self.assertEqual(c1.confirmation, 'NOT_CONFIRMED')

if __name__ == '__main__':
    unittest.main()
