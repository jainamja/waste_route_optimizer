import sqlite3

conn = sqlite3.connect('instance/waste_optimizer.db')
cursor = conn.cursor()
try:
    cursor.execute("SELECT customer_status FROM customers LIMIT 1")
    print("Column exists!")
except sqlite3.OperationalError as e:
    print(f"Error: {e}")
conn.close()
