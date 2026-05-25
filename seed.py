# seed.py — run with: python seed.py
import sqlite3
from data import HABITS, REWARDS

conn = sqlite3.connect("habits.db")
cur  = conn.cursor()

for i, h in enumerate(HABITS):
    exists = cur.execute(
        "SELECT id FROM habits WHERE name = ?", (h["name"],)
    ).fetchone()
    if not exists:
        cur.execute(
            """INSERT INTO habits (name, xp, pinned, schedule, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (h["name"], h["xp"], h.get("pinned", 0),
             h.get("schedule", "1111111"), i)
        )
        print(f"  Added habit: {h['name']}")
    else:
        # Update schedule and pinned if habit already exists
        cur.execute(
            """UPDATE habits SET pinned = ?, schedule = ?
               WHERE name = ?""",
            (h.get("pinned", 0), h.get("schedule", "1111111"), h["name"])
        )
        print(f"  Updated: {h['name']}")

for r in REWARDS:
    exists = cur.execute(
        "SELECT id FROM rewards WHERE name = ?", (r["name"],)
    ).fetchone()
    if not exists:
        cur.execute(
            "INSERT INTO rewards (name, cost) VALUES (?, ?)",
            (r["name"], r["cost"])
        )
        print(f"  Added reward: {r['name']}")
    else:
        print(f"  Skipped (exists): {r['name']}")

conn.commit()
conn.close()
print("\nSeeding complete.")