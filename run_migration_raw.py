import sqlite3

def run_migration():
    conn = sqlite3.connect('instance/routes.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE customers ADD COLUMN customer_status VARCHAR(20) DEFAULT 'ACTIVE';")
        conn.commit()
        print("Migrated successfully")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

run_migration()
