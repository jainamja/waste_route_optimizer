import sqlite3
import os

db_path = 'routes.db'
if os.path.exists('instance/routes.db'):
    db_path = 'instance/routes.db'

print(f"Using DB: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = c.fetchall()
    print(f"Tables: {tables}")
    
    if ('customers',) in tables or ('customer',) in tables:
        c.execute("PRAGMA table_info(customer);")
        print(f"Customer columns (if 'customer'): {c.fetchall()}")
        
        c.execute("PRAGMA table_info(customers);")
        print(f"Customer columns (if 'customers'): {c.fetchall()}")
except Exception as e:
    print(e)
