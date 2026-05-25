# migrate7.py — run ONCE, then delete
import sqlite3

conn = sqlite3.connect("habits.db")
cur  = conn.cursor()

# Todo lists
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS todo_lists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            reward_xp   INTEGER NOT NULL DEFAULT 0,
            completed   INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL
        )
    """)
    print("Created todo_lists")
except Exception as e:
    print(f"Skipped: {e}")

# Individual todo items
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS todo_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id     INTEGER NOT NULL,
            text        TEXT    NOT NULL,
            checked     INTEGER NOT NULL DEFAULT 0,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (list_id) REFERENCES todo_lists(id)
        )
    """)
    print("Created todo_items")
except Exception as e:
    print(f"Skipped: {e}")

conn.commit()
conn.close()
print("Migration 7 complete.")