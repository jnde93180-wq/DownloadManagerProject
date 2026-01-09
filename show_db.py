import sqlite3
from pathlib import Path

db = Path(__file__).parent / 'downloads.db'
if not db.exists():
    print('No downloads.db found')
    exit(0)

conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute('SELECT id, url, state, error, downloaded, total FROM downloads ORDER BY id DESC LIMIT 10')
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()
