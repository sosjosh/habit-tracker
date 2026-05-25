# migrate.py  — run ONCE, then delete this file
import sqlite3

conn = sqlite3.connect("habits.db")
cur = conn.cursor()

# 1. Add the new habit_logs table
cur.execute("""
    CREATE TABLE IF NOT EXISTS habit_logs (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id  INTEGER NOT NULL,
        timestamp TEXT    NOT NULL,          -- stored as ISO-8601: '2026-05-24 14:32:00'
        FOREIGN KEY (habit_id) REFERENCES habits(id)
    )
""")

# 2. Drop the now-redundant columns from habits
#    SQLite can't DROP COLUMN before v3.35, so we rebuild the table
cur.execute("ALTER TABLE habits RENAME TO habits_old")
cur.execute("""
    CREATE TABLE habits (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        name   TEXT    NOT NULL,
        xp     INTEGER NOT NULL DEFAULT 10,
        streak INTEGER NOT NULL DEFAULT 0
    )
""")
cur.execute("""
    INSERT INTO habits (id, name, xp, streak)
    SELECT id, name, xp, streak FROM habits_old
""")
cur.execute("DROP TABLE habits_old")

conn.commit()
conn.close()
print("Migration complete.")