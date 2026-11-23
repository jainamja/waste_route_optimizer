import os
import json
import pytest
from werkzeug.security import generate_password_hash

from waste_route_optimizer import (
    app, db, User, Customer, SavedTemplate, MasterCustomer,
    migrate_saved_template_customers_to_master
)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(username='admin_migration_tester').first()
        if not admin:
            admin = User(
                username='admin_migration_tester',
                password_hash=generate_password_hash('migratetestpass123'),
                role='ADMIN',
                name='Admin Migration Tester',
                is_superadmin=True
            )
            db.session.add(admin)
            db.session.commit()

        unauth_user = User.query.filter_by(username='restricted_driver').first()
        if not unauth_user:
            unauth_user = User(
                username='restricted_driver',
                password_hash=generate_password_hash('driverpass123'),
                role='DRIVER',
                name='Restricted Driver'
            )
            db.session.add(unauth_user)
            db.session.commit()

        admin_id = admin.id
        admin_username = admin.username

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['username'] = admin_username
            sess['role'] = 'ADMIN'
            sess['is_superadmin'] = True
        yield c

def test_migrate_extracts_all_template_customers():
    with app.app_context():
        # Setup clean test templates
        tmpl1 = SavedTemplate(
            name="Test Template Morning",
            customers_json=json.dumps([
                {
                    "id": 1001,
                    "name": "Acme Industrial",
                    "phone": "9876543210",
                    "address": "100 Industrial Area",
                    "location_url": "https://maps.google.com/?q=23.0100,72.5100",
                    "lat": 23.01,
                    "lng": 72.51,
                    "truck_id": 1,
                    "stop_number": 1,
                    "deliver_bag": True,
                    "geocode_quality": "EXACT",
                    "coord_source": "MANUAL",
                    "is_manually_corrected": True
                },
                {
                    "id": 1002,
                    "name": "Beacon Heights",
                    "phone": "9876543211",
                    "address": "200 Beacon Road",
                    "location_url": "https://maps.google.com/?q=23.0200,72.5200",
                    "lat": 23.02,
                    "lng": 72.52,
                    "truck_id": 1,
                    "stop_number": 2,
                    "deliver_bag": False
                }
            ]),
            is_assigned_instance=False
        )
        db.session.add(tmpl1)
        db.session.commit()

        stats = migrate_saved_template_customers_to_master()

        assert stats['success'] is True
        assert stats['processed'] >= 2
        assert stats['newly_added'] >= 2

        # Verify MasterCustomer exists
        c1 = MasterCustomer.query.filter_by(name="Acme Industrial").first()
        assert c1 is not None
        assert c1.phone == "9876543210"
        assert c1.address == "100 Industrial Area"
        assert c1.deliver_bag is True
        assert c1.lat == 23.01
        assert c1.lng == 72.51

        # Verify template stop updated with master_customer_id
        db.session.refresh(tmpl1)
        updated_custs = json.loads(tmpl1.customers_json)
        assert updated_custs[0]['master_customer_id'] == c1.id

        # Cleanup
        db.session.delete(tmpl1)
        db.session.delete(c1)
        c2 = MasterCustomer.query.filter_by(name="Beacon Heights").first()
        if c2: db.session.delete(c2)
        db.session.commit()

def test_deduplication_cross_templates_by_phone():
    with app.app_context():
        # Two templates with identical phone number for customer
        tmpl_a = SavedTemplate(
            name="Route Mon",
            customers_json=json.dumps([
                {
                    "id": 2001,
                    "name": "City Cafe",
                    "phone": "+91 98980-12345",
                    "address": "12 Market Street",
                    "location_url": "https://maps.google.com/?q=23.0300,72.5300",
                    "lat": 23.03,
                    "lng": 72.53,
                    "truck_id": 1,
                    "stop_number": 1
                }
            ]),
            is_assigned_instance=False
        )
        tmpl_b = SavedTemplate(
            name="Route Wed",
            customers_json=json.dumps([
                {
                    "id": 2002,
                    "name": "City Cafe - Central",
                    "phone": "09898012345",
                    "address": "12 Market St.",
                    "location_url": "https://maps.google.com/?q=23.0300,72.5300",
                    "lat": 23.03,
                    "lng": 72.53,
                    "truck_id": 1,
                    "stop_number": 1
                }
            ]),
            is_assigned_instance=False
        )
        db.session.add_all([tmpl_a, tmpl_b])
        db.session.commit()

        stats = migrate_saved_template_customers_to_master()

        # Both template stops share the same customer by normalized phone
        db.session.refresh(tmpl_a)
        db.session.refresh(tmpl_b)
        custs_a = json.loads(tmpl_a.customers_json)
        custs_b = json.loads(tmpl_b.customers_json)

        assert custs_a[0]['master_customer_id'] == custs_b[0]['master_customer_id']
        matching_mcs = MasterCustomer.query.filter(
            MasterCustomer.phone.in_(["+91 98980-12345", "09898012345", "9898012345"])
        ).all()
        # Exactly one master customer created
        assert len(matching_mcs) == 1

        # Cleanup
        db.session.delete(tmpl_a)
        db.session.delete(tmpl_b)
        for mc in matching_mcs: db.session.delete(mc)
        db.session.commit()

def test_different_customers_same_name_not_merged():
    with app.app_context():
        tmpl_x = SavedTemplate(
            name="North Route",
            customers_json=json.dumps([
                {
                    "id": 3001,
                    "name": "Amit Sharma",
                    "phone": "9111111111",
                    "address": "Sector 14, North Zone",
                    "location_url": "https://maps.google.com/?q=28.1000,77.1000",
                    "lat": 28.1,
                    "lng": 77.1,
                    "truck_id": 1,
                    "stop_number": 1
                }
            ]),
            is_assigned_instance=False
        )
        tmpl_y = SavedTemplate(
            name="South Route",
            customers_json=json.dumps([
                {
                    "id": 3002,
                    "name": "Amit Sharma",
                    "phone": "9222222222",
                    "address": "Indiranagar, South Zone",
                    "location_url": "https://maps.google.com/?q=12.9000,77.6000",
                    "lat": 12.9,
                    "lng": 77.6,
                    "truck_id": 1,
                    "stop_number": 1
                }
            ]),
            is_assigned_instance=False
        )
        db.session.add_all([tmpl_x, tmpl_y])
        db.session.commit()

        migrate_saved_template_customers_to_master()

        db.session.refresh(tmpl_x)
        db.session.refresh(tmpl_y)
        custs_x = json.loads(tmpl_x.customers_json)
        custs_y = json.loads(tmpl_y.customers_json)

        # Must NOT be merged into same master customer
        assert custs_x[0]['master_customer_id'] != custs_y[0]['master_customer_id']

        amits = MasterCustomer.query.filter_by(name="Amit Sharma").all()
        assert len(amits) >= 2

        # Cleanup
        db.session.delete(tmpl_x)
        db.session.delete(tmpl_y)
        for a in amits: db.session.delete(a)
        db.session.commit()

def test_idempotency_running_twice():
    with app.app_context():
        tmpl = SavedTemplate(
            name="Idempotency Test Route",
            customers_json=json.dumps([
                {
                    "id": 4001,
                    "name": "Repeat Customer",
                    "phone": "9444444444",
                    "address": "444 Repeat Ave",
                    "location_url": "https://maps.google.com/?q=23.4000,72.4000",
                    "lat": 23.4,
                    "lng": 72.4,
                    "truck_id": 1,
                    "stop_number": 1
                }
            ]),
            is_assigned_instance=False
        )
        db.session.add(tmpl)
        db.session.commit()

        # Run 1
        stats1 = migrate_saved_template_customers_to_master()
        count1 = MasterCustomer.query.count()

        # Run 2 immediately
        stats2 = migrate_saved_template_customers_to_master()
        count2 = MasterCustomer.query.count()

        # In run 2: zero new adds, total count unchanged
        assert stats2['newly_added'] == 0
        assert count1 == count2
        assert stats2['already_existing'] >= 1

        # Cleanup
        db.session.delete(tmpl)
        rc = MasterCustomer.query.filter_by(name="Repeat Customer").first()
        if rc: db.session.delete(rc)
        db.session.commit()

def test_legacy_incomplete_stops_handling_and_manual_review():
    with app.app_context():
        # Stop with missing address, phone, and url
        tmpl = SavedTemplate(
            name="Legacy Incomplete Route",
            customers_json=json.dumps([
                {
                    "id": 5001,
                    "name": "Legacy Stop 5001",
                    "lat": 28.51,
                    "lng": 77.21,
                    "truck_id": 1,
                    "stop_number": 1
                }
            ]),
            is_assigned_instance=False
        )
        db.session.add(tmpl)
        db.session.commit()

        stats = migrate_saved_template_customers_to_master()

        # Record must NOT be silently discarded
        mc = MasterCustomer.query.filter_by(name="Legacy Stop 5001").first()
        assert mc is not None
        assert "28.51" in mc.address
        assert "77.21" in mc.address
        assert mc.google_maps_url.startswith("https://www.google.com/maps")

        # Must be flagged in manual review items
        assert stats['requires_manual_review'] >= 1
        review_names = [item['name'] for item in stats['manual_review_items']]
        assert "Legacy Stop 5001" in review_names

        # Cleanup
        db.session.delete(tmpl)
        db.session.delete(mc)
        db.session.commit()

def test_depots_skipped():
    with app.app_context():
        tmpl = SavedTemplate(
            name="Depot Test Route",
            customers_json=json.dumps([
                {
                    "id": -1001,
                    "name": "End Location / Depot",
                    "lat": 23.0,
                    "lng": 72.0,
                    "truck_id": 1,
                    "stop_number": 2
                },
                {
                    "id": 6001,
                    "name": "Valid Stop Beside Depot",
                    "phone": "9555555555",
                    "address": "555 Normal St",
                    "location_url": "https://maps.google.com/?q=23.05,72.05",
                    "lat": 23.05,
                    "lng": 72.05,
                    "truck_id": 1,
                    "stop_number": 1
                }
            ]),
            is_assigned_instance=False
        )
        db.session.add(tmpl)
        db.session.commit()

        stats = migrate_saved_template_customers_to_master()

        # Depot is not created
        depot_mc = MasterCustomer.query.filter_by(name="End Location / Depot").first()
        assert depot_mc is None

        # Valid customer is created
        norm_mc = MasterCustomer.query.filter_by(name="Valid Stop Beside Depot").first()
        assert norm_mc is not None

        # Cleanup
        db.session.delete(tmpl)
        if norm_mc: db.session.delete(norm_mc)
        db.session.commit()

def test_admin_migration_api_endpoint(client):
    res = client.post('/api/admin/migrate_template_customers')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'processed' in data
    assert 'newly_added' in data
    assert 'already_existing' in data
    assert 'duplicates_skipped' in data
    assert 'requires_manual_review' in data

    status_res = client.get('/api/admin/migrate_template_customers/status')
    assert status_res.status_code == 200
    status_data = status_res.get_json()
    assert status_data['success'] is True
    assert 'master_customers_count' in status_data
    assert 'saved_templates_count' in status_data

def test_unauthorized_driver_cannot_migrate(client):
    with app.app_context():
        driver = User.query.filter_by(username='restricted_driver').first()
        driver_id = driver.id
        driver_username = driver.username

    with client.session_transaction() as sess:
        sess['user_id'] = driver_id
        sess['username'] = driver_username
        sess['role'] = 'DRIVER'
        sess.pop('is_superadmin', None)

    res = client.post('/api/admin/migrate_template_customers')
    assert res.status_code == 403

def test_template_route_deploy_after_migration(client):
    with app.app_context():
        tmpl = SavedTemplate(
            name="Deployability Verification Route",
            customers_json=json.dumps([
                {
                    "id": 7001,
                    "name": "Deploy Customer 1",
                    "phone": "9777777777",
                    "address": "777 Deploy St",
                    "location_url": "https://maps.google.com/?q=23.77,72.77",
                    "lat": 23.77,
                    "lng": 72.77,
                    "truck_id": 1,
                    "stop_number": 1
                }
            ]),
            metadata_json=json.dumps({"num_trucks": "1"}),
            is_assigned_instance=False
        )
        db.session.add(tmpl)
        db.session.commit()
        tmpl_id = tmpl.id

    # Run migration
    migrate_saved_template_customers_to_master()

    # Verify template can still be deployed via API
    with app.app_context():
        admin = User.query.filter_by(username='admin_migration_tester').first()
        admin_id = admin.id
        admin_username = admin.username

    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['username'] = admin_username
        sess['role'] = 'ADMIN'
        sess['is_superadmin'] = True

    deploy_res = client.post(f'/api/deploy_template/{tmpl_id}?mode=edit')
    assert deploy_res.status_code == 200

    with app.app_context():
        # Check Customer table got populated and contains master_customer_id
        deployed_c = Customer.query.filter_by(name="Deploy Customer 1").first()
        assert deployed_c is not None
        assert deployed_c.lat == 23.77
        assert deployed_c.lng == 72.77
        assert deployed_c.master_customer_id is not None

        # Clean up
        t_to_del = SavedTemplate.query.get(tmpl_id)
        if t_to_del: db.session.delete(t_to_del)
        mc_to_del = MasterCustomer.query.filter_by(name="Deploy Customer 1").first()
        if mc_to_del: db.session.delete(mc_to_del)
        Customer.query.filter_by(name="Deploy Customer 1").delete()
        db.session.commit()

