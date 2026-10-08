import sqlite3

conn = sqlite3.connect('instance/routes.db')
cursor = conn.cursor()
try:
    cursor.execute("SELECT customer_status FROM customers LIMIT 1")
    print("Column exists in instance/routes.db!")
except sqlite3.OperationalError as e:
    print(f"Error in instance: {e}")

try:
    conn2 = sqlite3.connect('routes.db')
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT customer_status FROM customer LIMIT 1")
    print("Column exists in routes.db!")
except sqlite3.OperationalError as e:
    print(f"Error in root: {e}")
