# migrate6.py — run ONCE, then delete
import sqlite3

conn = sqlite3.connect("habits.db")
cur  = conn.cursor()

try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS habit_skips (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id  INTEGER NOT NULL,
            timestamp TEXT    NOT NULL
        )
    """)
    print("Created habit_skips table")
except Exception as e:
    print(f"Skipped: {e}")

conn.commit()
conn.close()
print("Migration 6 complete.")