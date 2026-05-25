# migrate4.py — run ONCE, then delete
import sqlite3

conn = sqlite3.connect("habits.db")
cur  = conn.cursor()

# 1. redemption_logs for reward inventory
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS redemption_logs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            reward_id INTEGER NOT NULL,
            reward_name TEXT NOT NULL,
            cost      INTEGER NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    print("Created redemption_logs")
except Exception as e:
    print(f"Skipped: {e}")

# 2. freeze_spent_log — tracks auto-spent freezes so undo can reverse them
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS freeze_spent_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id     INTEGER NOT NULL,
            habit_log_id INTEGER NOT NULL
        )
    """)
    print("Created freeze_spent_logs")
except Exception as e:
    print(f"Skipped: {e}")

conn.commit()
conn.close()
print("Migration 4 complete.")