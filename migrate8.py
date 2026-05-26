# migrate8.py — run ONCE, then delete
import sqlite3

conn = sqlite3.connect("habits.db")
cur  = conn.cursor()

try:
    cur.execute(
        "ALTER TABLE habit_logs ADD COLUMN xp_earned INTEGER DEFAULT 0"
    )
    print("Added xp_earned to habit_logs")
except Exception as e:
    print(f"Skipped: {e}")

conn.commit()
conn.close()
print("Migration 8 complete.")