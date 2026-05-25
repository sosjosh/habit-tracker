# migrate3.py — run ONCE, then delete
import sqlite3

conn = sqlite3.connect("habits.db")
cur = conn.cursor()

# 1. Add streak_freezes to habits table
try:
    cur.execute("ALTER TABLE habits ADD COLUMN streak_freezes INTEGER DEFAULT 0")
    print("Added streak_freezes to habits")
except Exception as e:
    print(f"Skipped: {e}")

# 2. Remove streak_freezes from player (SQLite can't DROP COLUMN before 3.35
#    so we rebuild the table)
try:
    cur.execute("ALTER TABLE player RENAME TO player_old")
    cur.execute("""
        CREATE TABLE player (
            id       INTEGER PRIMARY KEY,
            total_xp INTEGER DEFAULT 0,
            level    INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        INSERT INTO player (id, total_xp, level)
        SELECT id, total_xp, level FROM player_old
    """)
    cur.execute("DROP TABLE player_old")
    print("Removed streak_freezes from player")
except Exception as e:
    print(f"Skipped player rebuild: {e}")

# 3. Create freeze_logs — tracks which habit_log entry earned a freeze
#    so undo can reverse it cleanly
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS freeze_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id     INTEGER NOT NULL,
            habit_log_id INTEGER NOT NULL,
            FOREIGN KEY (habit_id)     REFERENCES habits(id),
            FOREIGN KEY (habit_log_id) REFERENCES habit_logs(id)
        )
    """)
    print("Created freeze_logs table")
except Exception as e:
    print(f"Skipped freeze_logs: {e}")

conn.commit()
conn.close()
print("Migration 3 complete.")