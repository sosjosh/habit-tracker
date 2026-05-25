# migrate2.py — run ONCE, then delete
import sqlite3

conn = sqlite3.connect("habits.db")
cur = conn.cursor()

# Add freeze counter to player
try:
    cur.execute("ALTER TABLE player ADD COLUMN streak_freezes INTEGER DEFAULT 0")
    print("Added streak_freezes to player")
except Exception as e:
    print(f"Skipped (probably exists): {e}")

conn.commit()
conn.close()
print("Migration 2 complete.")