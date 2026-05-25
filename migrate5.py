# migrate5.py — run ONCE, then delete
import sqlite3

conn = sqlite3.connect("habits.db")
cur  = conn.cursor()

# 1. Add sort_order and pinned to habits
try:
    cur.execute("ALTER TABLE habits ADD COLUMN sort_order INTEGER DEFAULT 0")
    print("Added sort_order to habits")
except Exception as e:
    print(f"Skipped: {e}")

try:
    cur.execute("ALTER TABLE habits ADD COLUMN pinned INTEGER DEFAULT 0")
    print("Added pinned to habits")
except Exception as e:
    print(f"Skipped: {e}")

# 2. Add schedule to habits
# 7-character string "MTWTFSS", 1 = active that day, 0 = skip
# Default "1111111" = every day
try:
    cur.execute("ALTER TABLE habits ADD COLUMN schedule TEXT DEFAULT '1111111'")
    print("Added schedule to habits")
except Exception as e:
    print(f"Skipped: {e}")

# 3. Add notes column to habit_logs
try:
    cur.execute("ALTER TABLE habit_logs ADD COLUMN note TEXT DEFAULT ''")
    print("Added note to habit_logs")
except Exception as e:
    print(f"Skipped: {e}")

# 4. Set initial sort_order to match current id order
cur.execute("""
    UPDATE habits SET sort_order = id
""")

conn.commit()
conn.close()
print("Migration 5 complete.")