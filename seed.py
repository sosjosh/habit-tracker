# seed.py — run with: python3 seed.py
# Safe to re-run: skips items that already exist by name.

import sqlite3
from data import HABITS, REWARDS

conn = sqlite3.connect("habits.db")
cur = conn.cursor()

for h in HABITS:
    exists = cur.execute(
        "SELECT id FROM habits WHERE name = ?", (h["name"],)
    ).fetchone()
    if not exists:
        cur.execute(
            "INSERT INTO habits (name, xp) VALUES (?, ?)",
            (h["name"], h["xp"])
        )
        print(f"  Added habit:  {h['name']}")
    else:
        print(f"  Skipped (exists): {h['name']}")

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