import sqlite3
c=sqlite3.connect('routes.db')
print(c.execute("PRAGMA table_info(customers);").fetchall())
