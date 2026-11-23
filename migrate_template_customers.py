#!/usr/bin/env python3
"""
CLI runner for migrating and synchronizing customers from SavedTemplate records
into the MasterCustomer database (master_customers table).

Usage:
    python migrate_template_customers.py [--dry-run]
"""

import sys
import os
import json
import argparse

# Add repo to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from waste_route_optimizer import app, db, SavedTemplate, MasterCustomer, migrate_saved_template_customers_to_master

def main():
    parser = argparse.ArgumentParser(description="Migrate and sync template customers into Master Customer List.")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    with app.app_context():
        print("=================================================================")
        print(" TrashTrekyx — Saved Template to Master Customer Migration")
        print("=================================================================")

        before_master = MasterCustomer.query.count()
        before_templates = SavedTemplate.query.count()
        print(f"Templates in database:        {before_templates}")
        print(f"Master Customers before sync: {before_master}")
        print("Executing migration...")

        stats = migrate_saved_template_customers_to_master()

        after_master = MasterCustomer.query.count()
        print("\n---------------------- Migration Summary ----------------------")
        print(f"Templates Scanned:            {stats['templates_scanned']}")
        print(f"Total Customer Stops Read:    {stats['processed']}")
        print(f"Newly Added to Master List:   {stats['newly_added']}")
        print(f"Already Existing in Master:   {stats['already_existing']}")
        print(f"Cross-Template Dups Skipped:  {stats['duplicates_skipped']}")
        print(f"Records Requiring Review:     {stats['requires_manual_review']}")
        print(f"Master Customers after sync:  {after_master} (+{after_master - before_master})")
        print("---------------------------------------------------------------")

        if stats['manual_review_items']:
            print("\nRecords Requiring Manual Review:")
            for item in stats['manual_review_items']:
                print(f"  * [Template: {item['template_name']}] Stop: '{item['name']}' (Master ID: {item['master_customer_id']})")
                print(f"    Address: {item['address']}")
                print(f"    Phone:   {item['phone']}")
                print(f"    URL:     {item['google_maps_url']}")
                print(f"    Coords:  ({item['lat']}, {item['lng']})")
                print(f"    Reasons: {'; '.join(item['reasons'])}")

        if args.json:
            print("\nJSON Output:")
            print(json.dumps(stats, indent=2))

        print("\nMigration completed successfully.")
        return 0

if __name__ == '__main__':
    sys.exit(main())
