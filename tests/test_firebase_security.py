import unittest
import json
import jwt
from werkzeug.security import generate_password_hash

import waste_route_optimizer as w
from waste_route_optimizer import (
    app, db, User, Customer,
    generate_auth_token, verify_auth_token,
    create_firebase_custom_token
)

class RuleContext:
    """Helper to simulate Firebase Realtime Database Security Rule evaluations."""
    def __init__(self, auth=None, path_vars=None, current_data=None, new_data=None):
        self.auth = auth
        self.path_vars = path_vars or {}
        self.current_data = current_data
        self.new_data = new_data

    def evaluate_rule_expr(self, expr_str, value=None):
        if expr_str is False:
            return False
        if expr_str is True:
            return True
        if not isinstance(expr_str, str):
            return bool(expr_str)

        # Build execution environment modeling Firebase RTDB rule context
        class LooseValue:
            def __init__(self, val):
                self.val = val
            def __eq__(self, other):
                if hasattr(other, 'val'):
                    other = other.val
                if self.val is None or other is None:
                    return self.val is other
                return str(self.val) == str(other)
            def __ne__(self, other):
                return not self.__eq__(other)
            def __add__(self, other):
                return str(self.val) + str(other)
            def __radd__(self, other):
                return str(other) + str(self.val)
            def __str__(self):
                return str(self.val)
            def __repr__(self):
                return repr(self.val)

        class AuthToken:
            def __init__(self, token_dict):
                self._d = token_dict or {}
                self.role = self._d.get('role')
                self.truck_id = LooseValue(self._d.get('truck_id')) if self._d.get('truck_id') is not None else None
                self.driver_id = LooseValue(self._d.get('driver_id')) if self._d.get('driver_id') is not None else None
                self.admin_id = LooseValue(self._d.get('admin_id')) if self._d.get('admin_id') is not None else None

        class AuthObj:
            def __init__(self, auth_dict):
                if auth_dict is None:
                    self.token = None
                    self.uid = None
                else:
                    self.uid = LooseValue(auth_dict.get('uid'))
                    self.token = AuthToken(auth_dict.get('token', {}))

        class DataSnap:
            def __init__(self, val):
                self._val = val
            def val(self):
                return self._val
            def exists(self):
                return self._val is not None
            def isNumber(self):
                return isinstance(self._val, (int, float)) and not isinstance(self._val, bool)
            def isString(self):
                return isinstance(self._val, str)
            def isBoolean(self):
                return isinstance(self._val, bool)
            def hasChildren(self, keys):
                if isinstance(self._val, dict):
                    return any(k in self._val for k in keys)
                return False

        eval_globals = {
            'auth': AuthObj(self.auth) if self.auth is not None else None,
            'data': DataSnap(self.current_data),
            'newData': DataSnap(value if value is not None else self.new_data),
            'null': None,
            'true': True,
            'false': False
        }

        # Convert JS-style operators to Python
        py_expr = expr_str.replace('&&', ' and ').replace('||', ' or ').replace('===', '==').replace('!==', '!=')
        for k, v in self.path_vars.items():
            var_name = 'var_' + k
            eval_globals[var_name] = LooseValue(v)
            py_expr = py_expr.replace('$' + k, var_name)

        try:
            return bool(eval(py_expr, eval_globals))
        except Exception as e:
            return False


class TestFirebaseSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open('firebase.database.rules.json', 'r', encoding='utf-8') as f:
            cls.rules_json = json.load(f)['rules']

    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Admin User
        admin = User.query.filter_by(username='fb_sec_admin').first()
        if not admin:
            admin = User(
                username='fb_sec_admin',
                password_hash=generate_password_hash('AdminPass@2026'),
                role='ADMIN',
                name='Firebase Admin'
            )
            db.session.add(admin)
            db.session.commit()
        self.admin = admin

        # Driver 1 (Truck 71)
        d1 = User.query.filter_by(username='fb_driver_71').first()
        if not d1:
            d1 = User(
                username='fb_driver_71',
                password_hash=generate_password_hash('Driver71Pass'),
                role='DRIVER',
                name='Driver 71',
                truck_id=71
            )
            db.session.add(d1)
        else:
            d1.truck_id = 71
        db.session.commit()
        self.driver1 = d1

        # Driver 2 (Truck 72)
        d2 = User.query.filter_by(username='fb_driver_72').first()
        if not d2:
            d2 = User(
                username='fb_driver_72',
                password_hash=generate_password_hash('Driver72Pass'),
                role='DRIVER',
                name='Driver 72',
                truck_id=72
            )
            db.session.add(d2)
        else:
            d2.truck_id = 72
        db.session.commit()
        self.driver2 = d2

    def tearDown(self):
        self.ctx.pop()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            User.query.filter(User.username.in_(['fb_sec_admin', 'fb_driver_71', 'fb_driver_72'])).delete()
            Customer.query.filter(Customer.truck_id.in_([71, 72])).delete()
            db.session.commit()

    # =========================================================================
    # PART 1: SERVER-SIDE FIREBASE CUSTOM TOKEN GENERATION TESTS
    # =========================================================================

    def test_unauthenticated_custom_token_request_returns_401(self):
        res = self.client.get('/api/firebase_custom_token')
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn('error', data)

    def test_numeric_id_token_rejected_for_custom_token(self):
        for raw_id in ['1', '2', '100', str(self.admin.id), str(self.driver1.id)]:
            res = self.client.get(f'/api/firebase_custom_token?token={raw_id}')
            self.assertEqual(res.status_code, 401)

            res_header = self.client.get(
                '/api/firebase_custom_token',
                headers={'Authorization': f'Bearer {raw_id}'}
            )
            self.assertEqual(res_header.status_code, 401)

    def test_tampered_token_rejected_for_custom_token(self):
        token = generate_auth_token(self.driver1)
        tampered = token[:-4] + 'xxxx'
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {tampered}'}
        )
        self.assertEqual(res.status_code, 401)

    def test_valid_driver_receives_verified_custom_token(self):
        token = generate_auth_token(self.driver1)
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('firebase_custom_token', data)
        custom_token = data['firebase_custom_token']

        # Verify claims returned by server
        claims = data['claims']
        self.assertEqual(claims['role'], 'DRIVER')
        self.assertEqual(str(claims['driver_id']), str(self.driver1.id))
        self.assertEqual(str(claims['truck_id']), '71')

        # Decode JWT (unverified signature to inspect payload structure)
        payload = jwt.decode(custom_token, options={'verify_signature': False})
        self.assertEqual(payload['uid'], f"user_{self.driver1.id}")
        self.assertEqual(payload['claims']['role'], 'DRIVER')
        self.assertEqual(str(payload['claims']['truck_id']), '71')
        self.assertEqual(str(payload['claims']['driver_id']), str(self.driver1.id))
        self.assertEqual(payload['aud'], 'https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit')
        self.assertTrue(payload['exp'] > payload['iat'])

    def test_client_cannot_forge_truck_or_role_claims(self):
        # Malicious driver attempts to pass truck_id=999 and role=ADMIN in request
        token = generate_auth_token(self.driver1)
        res = self.client.post(
            '/api/firebase_custom_token?truck_id=999&role=ADMIN',
            headers={'Authorization': f'Bearer {token}'},
            json={'truck_id': 999, 'role': 'ADMIN', 'claims': {'role': 'ADMIN'}}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        # Server must strictly enforce database-backed claims
        self.assertEqual(data['claims']['role'], 'DRIVER')
        self.assertEqual(str(data['claims']['truck_id']), '71')
        self.assertEqual(str(data['claims']['driver_id']), str(self.driver1.id))

        payload = jwt.decode(data['firebase_custom_token'], options={'verify_signature': False})
        self.assertEqual(payload['claims']['role'], 'DRIVER')
        self.assertEqual(str(payload['claims']['truck_id']), '71')

    def test_driver_truck_reassignment_updates_token_claims(self):
        token = generate_auth_token(self.driver1)
        
        # Admin reassigns Driver 1 to Truck 75
        self.driver1.truck_id = 75
        db.session.commit()

        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(str(data['claims']['truck_id']), '75')

        # Restore truck_id
        self.driver1.truck_id = 71
        db.session.commit()

    def test_valid_admin_receives_admin_claims(self):
        token = generate_auth_token(self.admin)
        res = self.client.get(
            '/api/firebase_custom_token',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['claims']['role'], 'ADMIN')
        self.assertEqual(str(data['claims']['admin_id']), str(self.admin.id))

        payload = jwt.decode(data['firebase_custom_token'], options={'verify_signature': False})
        self.assertEqual(payload['claims']['role'], 'ADMIN')

    # =========================================================================
    # PART 2: FIREBASE REALTIME DATABASE SECURITY RULES VERIFICATION
    # =========================================================================

    def test_rules_unauthenticated_access_denied_everywhere(self):
        # Context with auth = None
        ctx = RuleContext(auth=None)
        
        # Root read/write
        self.assertFalse(ctx.evaluate_rule_expr(self.rules_json['.read']))
        self.assertFalse(ctx.evaluate_rule_expr(self.rules_json['.write']))

        # Trucks read/write
        truck_rule = self.rules_json['trucks']['$truckId']
        ctx_truck = RuleContext(auth=None, path_vars={'truckId': '71'})
        self.assertFalse(ctx_truck.evaluate_rule_expr(truck_rule['.read']))
        self.assertFalse(ctx_truck.evaluate_rule_expr(truck_rule['.write']))

        # Routes read/write
        route_rule = self.rules_json['routes']['$routeKey']
        ctx_route = RuleContext(auth=None, path_vars={'routeKey': 'route_71'})
        self.assertFalse(ctx_route.evaluate_rule_expr(route_rule['.read']))
        self.assertFalse(ctx_route.evaluate_rule_expr(route_rule['.write']))

        # System status & settings
        system_status_rule = self.rules_json['system_status']
        self.assertFalse(ctx.evaluate_rule_expr(system_status_rule['.read']))
        self.assertFalse(ctx.evaluate_rule_expr(system_status_rule['.write']))

        settings_rule = self.rules_json['settings']
        self.assertFalse(ctx.evaluate_rule_expr(settings_rule['.read']))
        self.assertFalse(ctx.evaluate_rule_expr(settings_rule['.write']))

    def test_rules_driver_can_read_and_write_own_truck_gps(self):
        driver1_auth = {
            'uid': f'user_{self.driver1.id}',
            'token': {'role': 'DRIVER', 'truck_id': '71', 'driver_id': str(self.driver1.id)}
        }
        ctx_own = RuleContext(auth=driver1_auth, path_vars={'truckId': '71'})
        truck_rule = self.rules_json['trucks']['$truckId']

        # Reading own truck -> ALLOWED
        self.assertTrue(ctx_own.evaluate_rule_expr(truck_rule['.read']))
        # Writing to truck root -> DENIED (Admin only; driver cannot overwrite truck configuration)
        self.assertFalse(ctx_own.evaluate_rule_expr(truck_rule['.write']))
        # Writing to permitted GPS telemetry fields -> ALLOWED
        self.assertTrue(ctx_own.evaluate_rule_expr(truck_rule['currentLat']['.write']))
        self.assertTrue(ctx_own.evaluate_rule_expr(truck_rule['currentLng']['.write']))
        self.assertTrue(ctx_own.evaluate_rule_expr(truck_rule['speed']['.write']))
        self.assertTrue(ctx_own.evaluate_rule_expr(truck_rule['status']['.write']))

    def test_rules_driver_cannot_access_or_modify_other_truck_gps(self):
        # Driver 1 (truck 71) attempts to access Truck 72
        driver1_auth = {
            'uid': f'user_{self.driver1.id}',
            'token': {'role': 'DRIVER', 'truck_id': '71', 'driver_id': str(self.driver1.id)}
        }
        ctx_other = RuleContext(auth=driver1_auth, path_vars={'truckId': '72'})
        truck_rule = self.rules_json['trucks']['$truckId']

        # Reading other truck -> DENIED
        self.assertFalse(ctx_other.evaluate_rule_expr(truck_rule['.read']))
        # Writing to other truck -> DENIED
        self.assertFalse(ctx_other.evaluate_rule_expr(truck_rule['.write']))
        self.assertFalse(ctx_other.evaluate_rule_expr(truck_rule['currentLat']['.write']))

    def test_rules_driver_cannot_read_all_trucks_or_routes(self):
        driver1_auth = {
            'uid': f'user_{self.driver1.id}',
            'token': {'role': 'DRIVER', 'truck_id': '71', 'driver_id': str(self.driver1.id)}
        }
        ctx = RuleContext(auth=driver1_auth)

        # Listing all trucks -> DENIED
        self.assertFalse(ctx.evaluate_rule_expr(self.rules_json['trucks']['.read']))
        # Listing all routes -> DENIED
        self.assertFalse(ctx.evaluate_rule_expr(self.rules_json['routes']['.read']))
        # Reading/writing system status -> DENIED
        self.assertFalse(ctx.evaluate_rule_expr(self.rules_json['system_status']['.read']))
        self.assertFalse(ctx.evaluate_rule_expr(self.rules_json['system_status']['.write']))
        # Reading/writing settings -> DENIED
        self.assertFalse(ctx.evaluate_rule_expr(self.rules_json['settings']['.read']))
        self.assertFalse(ctx.evaluate_rule_expr(self.rules_json['settings']['.write']))

    def test_rules_gps_validation_rejects_out_of_bounds_coordinates_or_bad_status(self):
        truck_rule = self.rules_json['trucks']['$truckId']
        driver1_auth = {
            'uid': f'user_{self.driver1.id}',
            'token': {'role': 'DRIVER', 'truck_id': '71', 'driver_id': str(self.driver1.id)}
        }
        ctx = RuleContext(auth=driver1_auth, path_vars={'truckId': '71'})

        # Valid coordinates
        self.assertTrue(ctx.evaluate_rule_expr(truck_rule['currentLat']['.validate'], value=23.0225))
        self.assertTrue(ctx.evaluate_rule_expr(truck_rule['currentLng']['.validate'], value=72.5714))
        self.assertTrue(ctx.evaluate_rule_expr(truck_rule['status']['.validate'], value='online'))
        self.assertTrue(ctx.evaluate_rule_expr(truck_rule['speed']['.validate'], value=45.5))
        self.assertTrue(ctx.evaluate_rule_expr(truck_rule['heading']['.validate'], value=180))

        # Invalid latitude (> 90 or < -90)
        self.assertFalse(ctx.evaluate_rule_expr(truck_rule['currentLat']['.validate'], value=120.5))
        self.assertFalse(ctx.evaluate_rule_expr(truck_rule['currentLat']['.validate'], value=-95.0))

        # Invalid longitude (> 180 or < -180)
        self.assertFalse(ctx.evaluate_rule_expr(truck_rule['currentLng']['.validate'], value=200.0))

        # Invalid status
        self.assertFalse(ctx.evaluate_rule_expr(truck_rule['status']['.validate'], value='MALICIOUS_STATUS'))

        # Negative speed
        self.assertFalse(ctx.evaluate_rule_expr(truck_rule['speed']['.validate'], value=-10.0))

    def test_rules_driver_can_update_own_route_stop_status_only(self):
        driver1_auth = {
            'uid': f'user_{self.driver1.id}',
            'token': {'role': 'DRIVER', 'truck_id': '71', 'driver_id': str(self.driver1.id)}
        }
        ctx_own = RuleContext(auth=driver1_auth, path_vars={'routeKey': 'route_71', 'stopId': '1001'})
        route_rule = self.rules_json['routes']['$routeKey']
        stop_rule = route_rule['stops']['$stopId']

        # Driver can read own route
        self.assertTrue(ctx_own.evaluate_rule_expr(route_rule['.read']))

        # Driver cannot delete or overwrite root route node
        self.assertFalse(ctx_own.evaluate_rule_expr(route_rule['.write']))

        # Driver cannot overwrite stop node
        self.assertFalse(ctx_own.evaluate_rule_expr(stop_rule['.write']))

        # Driver CAN update stop status
        self.assertTrue(ctx_own.evaluate_rule_expr(stop_rule['status']['.write']))

        # Stop status validations
        self.assertTrue(ctx_own.evaluate_rule_expr(stop_rule['status']['.validate'], value='COMPLETED'))
        self.assertTrue(ctx_own.evaluate_rule_expr(stop_rule['status']['.validate'], value='SKIPPED'))
        self.assertTrue(ctx_own.evaluate_rule_expr(stop_rule['status']['.validate'], value='PENDING'))
        self.assertFalse(ctx_own.evaluate_rule_expr(stop_rule['status']['.validate'], value='ARBITRARY_INJECTION'))

    def test_rules_driver_cannot_update_other_truck_stops(self):
        # Driver 1 attempts to update Truck 72 stop
        driver1_auth = {
            'uid': f'user_{self.driver1.id}',
            'token': {'role': 'DRIVER', 'truck_id': '71', 'driver_id': str(self.driver1.id)}
        }
        ctx_other = RuleContext(auth=driver1_auth, path_vars={'routeKey': 'route_72', 'stopId': '2001'})
        route_rule = self.rules_json['routes']['$routeKey']
        stop_rule = route_rule['stops']['$stopId']

        # Reading other route -> DENIED
        self.assertFalse(ctx_other.evaluate_rule_expr(route_rule['.read']))
        # Updating other stop -> DENIED
        self.assertFalse(ctx_other.evaluate_rule_expr(stop_rule['status']['.write']))

    def test_rules_admin_can_access_all_trucks_and_routes(self):
        admin_auth = {
            'uid': f'user_{self.admin.id}',
            'token': {'role': 'ADMIN', 'admin_id': str(self.admin.id)}
        }
        ctx_trucks = RuleContext(auth=admin_auth)
        ctx_truck71 = RuleContext(auth=admin_auth, path_vars={'truckId': '71'})
        ctx_routes = RuleContext(auth=admin_auth)
        ctx_route71 = RuleContext(auth=admin_auth, path_vars={'routeKey': 'route_71'})

        # Admin can read all trucks
        self.assertTrue(ctx_trucks.evaluate_rule_expr(self.rules_json['trucks']['.read']))
        # Admin can read any individual truck
        self.assertTrue(ctx_truck71.evaluate_rule_expr(self.rules_json['trucks']['$truckId']['.read']))
        # Admin can write any individual truck
        self.assertTrue(ctx_truck71.evaluate_rule_expr(self.rules_json['trucks']['$truckId']['.write']))

        # Admin can read all routes
        self.assertTrue(ctx_routes.evaluate_rule_expr(self.rules_json['routes']['.read']))
        # Admin can write any route
        self.assertTrue(ctx_route71.evaluate_rule_expr(self.rules_json['routes']['$routeKey']['.write']))

        # Admin can read and write settings & system_status
        self.assertTrue(ctx_trucks.evaluate_rule_expr(self.rules_json['system_status']['.read']))
        self.assertTrue(ctx_trucks.evaluate_rule_expr(self.rules_json['system_status']['.write']))
        self.assertTrue(ctx_trucks.evaluate_rule_expr(self.rules_json['settings']['.read']))
        self.assertTrue(ctx_trucks.evaluate_rule_expr(self.rules_json['settings']['.write']))

    def test_rules_driver_locations_isolated_by_driver_id(self):
        d1_auth = {
            'uid': f'user_{self.driver1.id}',
            'token': {'role': 'DRIVER', 'driver_id': str(self.driver1.id), 'truck_id': '71'}
        }
        loc_rule = self.rules_json['driver_locations']['$driverId']

        ctx_own = RuleContext(auth=d1_auth, path_vars={'driverId': str(self.driver1.id)})
        self.assertTrue(ctx_own.evaluate_rule_expr(loc_rule['.read']))
        # Parent driver location write is Admin only (driver cannot delete or overwrite root node)
        self.assertFalse(ctx_own.evaluate_rule_expr(loc_rule['.write']))
        # Telemetry child field write is allowed
        self.assertTrue(ctx_own.evaluate_rule_expr(loc_rule['currentLat']['.write']))

        ctx_other = RuleContext(auth=d1_auth, path_vars={'driverId': str(self.driver2.id)})
        self.assertFalse(ctx_other.evaluate_rule_expr(loc_rule['.read']))
        self.assertFalse(ctx_other.evaluate_rule_expr(loc_rule['.write']))
        self.assertFalse(ctx_other.evaluate_rule_expr(loc_rule['currentLat']['.write']))

if __name__ == '__main__':
    unittest.main()
