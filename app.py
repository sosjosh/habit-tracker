from flask import Flask, render_template, request, redirect, url_for, g, flash
import sqlite3
import math
from datetime import datetime, date, timedelta

app = Flask(__name__)
app.secret_key = "habitquest-secret-key"  # needed for flash messages
DATABASE = "habits.db"


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name   TEXT    NOT NULL,
            xp     INTEGER NOT NULL DEFAULT 10,
            streak INTEGER NOT NULL DEFAULT 0
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id  INTEGER NOT NULL,
            timestamp TEXT    NOT NULL,
            FOREIGN KEY (habit_id) REFERENCES habits(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS player (
            id              INTEGER PRIMARY KEY,
            total_xp        INTEGER DEFAULT 0,
            level           INTEGER DEFAULT 1,
            streak_freezes  INTEGER DEFAULT 0
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT    NOT NULL,
            cost INTEGER NOT NULL
        )
    """)

    existing_player = db.execute("SELECT * FROM player WHERE id = 1").fetchone()
    if not existing_player:
        db.execute("INSERT INTO player (id, total_xp, level, streak_freezes) VALUES (1, 0, 1, 0)")

    db.commit()


# ─────────────────────────────────────────────
# XP / LEVEL
# ─────────────────────────────────────────────

def calculate_level(total_xp):
    return max(1, int(math.sqrt(total_xp / 100)) + 1)

def xp_for_next_level(level):
    return (level ** 2) * 100


# ─────────────────────────────────────────────
# STREAK & LOG HELPERS
# ─────────────────────────────────────────────

def get_today():
    return date.today()

def log_completion(habit_id):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO habit_logs (habit_id, timestamp) VALUES (?, ?)",
        (habit_id, now)
    )
    db.commit()

def calculate_streak(habit_id):
    """
    Walk backwards through distinct completion dates.
    If a single-day gap is found and the habit has a freeze available,
    spend it automatically and continue the streak.
    """
    db = get_db()
    rows = db.execute("""
        SELECT DISTINCT date(timestamp) AS day
        FROM habit_logs
        WHERE habit_id = ?
        ORDER BY day DESC
    """, (habit_id,)).fetchall()

    if not rows:
        return 0

    today    = get_today()
    streak   = 0
    expected = today
    freeze_used = False  # only auto-spend one freeze per calculation

    for row in rows:
        day = date.fromisoformat(row["day"])

        # Streak is dead if last completion was 2+ days ago
        # (unless we haven't started counting yet)
        if streak == 0 and day < today - timedelta(days=1):
            return 0

        if day == expected:
            streak += 1
            expected -= timedelta(days=1)

        elif day == expected - timedelta(days=1) and not freeze_used:
            # Exactly one day gap — check if habit has a freeze to spend
            habit = db.execute(
                "SELECT streak_freezes FROM habits WHERE id = ?", (habit_id,)
            ).fetchone()

            if habit and habit["streak_freezes"] > 0:
                # Spend the freeze, bridge the gap, continue counting
                db.execute(
                    "UPDATE habits SET streak_freezes = streak_freezes - 1 WHERE id = ?",
                    (habit_id,)
                )
                db.commit()
                freeze_used = True
                streak += 2          # the missed day + the found day
                expected = day - timedelta(days=1)
            else:
                break  # gap and no freeze — streak ends

        else:
            break  # gap larger than 1 day, or no freeze left

    return streak

def completions_today(habit_id):
    db = get_db()
    today = get_today().isoformat()
    row = db.execute("""
        SELECT COUNT(*) AS cnt
        FROM habit_logs
        WHERE habit_id = ?
          AND date(timestamp) = ?
    """, (habit_id, today)).fetchone()
    return row["cnt"]


# ─────────────────────────────────────────────
# STREAK FREEZE HELPER
# Award one freeze every 5 completions across all habits today.
# Tracked by comparing total log entries to freezes already awarded.
# ─────────────────────────────────────────────

def maybe_award_freeze(habit_id, habit_log_id):
    """
    Award a freeze to this specific habit every 5 completions of that habit.
    Ties the award to the habit_log_id so undo_habit can reverse it.
    Returns True if a freeze was awarded.
    """
    db = get_db()

    # Count total completions for this habit
    total = db.execute(
        "SELECT COUNT(*) AS cnt FROM habit_logs WHERE habit_id = ?",
        (habit_id,)
    ).fetchone()["cnt"]

    # Count freezes already awarded to this habit
    awarded_so_far = db.execute(
        "SELECT COUNT(*) AS cnt FROM freeze_logs WHERE habit_id = ?",
        (habit_id,)
    ).fetchone()["cnt"]

    freezes_earned = total // 5

    if freezes_earned > awarded_so_far:
        # Award one freeze and record which log entry triggered it
        db.execute(
            "UPDATE habits SET streak_freezes = streak_freezes + 1 WHERE id = ?",
            (habit_id,)
        )
        db.execute(
            "INSERT INTO freeze_logs (habit_id, habit_log_id) VALUES (?, ?)",
            (habit_id, habit_log_id)
        )
        db.commit()
        return True

    return False


@app.route("/complete/<int:habit_id>", methods=["POST"])
def complete_habit(habit_id):
    db    = get_db()
    habit = db.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()

    if not habit:
        return redirect(url_for("home"))

    # Write log and get its id
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.execute(
        "INSERT INTO habit_logs (habit_id, timestamp) VALUES (?, ?)",
        (habit_id, now)
    )
    db.commit()
    new_log_id = cursor.lastrowid  # the id of the log we just inserted

    new_streak = calculate_streak(habit_id)
    db.execute("UPDATE habits SET streak = ? WHERE id = ?", (new_streak, habit_id))

    player    = db.execute("SELECT * FROM player WHERE id = 1").fetchone()
    new_xp    = player["total_xp"] + habit["xp"]
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )
    db.commit()

    awarded = maybe_award_freeze(habit_id, new_log_id)
    if awarded:
        flash(f"🧊 Streak freeze earned for <strong>{habit['name']}</strong>!", "freeze")

    flash(f"✅ Completed <strong>{habit['name']}</strong> — +{habit['xp']} XP!", "success")
    return redirect(url_for("home"))


@app.route("/undo_habit/<int:habit_id>", methods=["POST"])
def undo_habit(habit_id):
    db = get_db()

    last_log = db.execute("""
        SELECT id FROM habit_logs
        WHERE habit_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (habit_id,)).fetchone()

    if not last_log:
        flash("Nothing to undo.", "info")
        return redirect(url_for("home"))

    log_id = last_log["id"]

    # Check if this log entry triggered a freeze award — if so, reverse it
    freeze_entry = db.execute(
        "SELECT id FROM freeze_logs WHERE habit_log_id = ?", (log_id,)
    ).fetchone()

    if freeze_entry:
        db.execute("DELETE FROM freeze_logs WHERE id = ?", (freeze_entry["id"],))
        db.execute(
            "UPDATE habits SET streak_freezes = MAX(0, streak_freezes - 1) WHERE id = ?",
            (habit_id,)
        )

    db.execute("DELETE FROM habit_logs WHERE id = ?", (log_id,))

    new_streak = calculate_streak(habit_id)
    habit      = db.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    db.execute("UPDATE habits SET streak = ? WHERE id = ?", (new_streak, habit_id))

    player    = db.execute("SELECT total_xp FROM player WHERE id = 1").fetchone()
    new_xp    = max(0, player["total_xp"] - habit["xp"])
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )
    db.commit()

    flash(f"↩️ Undid <strong>{habit['name']}</strong> — -{habit['xp']} XP.", "info")
    return redirect(url_for("home"))


# @app.route("/delete_habit/<int:habit_id>", methods=["POST"])
# def delete_habit(habit_id):
#     db    = get_db()
#     habit = db.execute("SELECT name FROM habits WHERE id = ?", (habit_id,)).fetchone()
#     db.execute("DELETE FROM habit_logs WHERE habit_id = ?", (habit_id,))
#     db.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
#     db.commit()
#     flash(f"🗑️ Deleted habit <strong>{habit['name']}</strong>.", "info")
#     return redirect(url_for("home"))


@app.route("/redeem/<int:reward_id>", methods=["POST"])
def redeem_reward(reward_id):
    db     = get_db()
    reward = db.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,)).fetchone()
    player = db.execute("SELECT * FROM player WHERE id = 1").fetchone()

    if not reward:
        return redirect(url_for("home"))

    if player["total_xp"] < reward["cost"]:
        flash(f"❌ Not enough XP to redeem <strong>{reward['name']}</strong>. Need {reward['cost']} XP.", "error")
        return redirect(url_for("home"))

    new_xp    = player["total_xp"] - reward["cost"]
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )
    db.commit()

    flash(f"🎁 Redeemed <strong>{reward['name']}</strong> for {reward['cost']} XP!", "success")
    return redirect(url_for("home"))


@app.route("/undo_reward/<int:reward_id>", methods=["POST"])
def undo_reward(reward_id):
    db     = get_db()
    reward = db.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,)).fetchone()
    player = db.execute("SELECT * FROM player WHERE id = 1").fetchone()

    if reward:
        new_xp    = player["total_xp"] + reward["cost"]
        new_level = calculate_level(new_xp)
        db.execute(
            "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
            (new_xp, new_level)
        )
        db.commit()
        flash(f"↩️ Undid redemption of <strong>{reward['name']}</strong> — +{reward['cost']} XP returned.", "info")

    return redirect(url_for("home"))


# @app.route("/delete_reward/<int:reward_id>", methods=["POST"])
# def delete_reward(reward_id):
#     db     = get_db()
#     reward = db.execute("SELECT name FROM rewards WHERE id = ?", (reward_id,)).fetchone()
#     db.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
#     db.commit()
#     flash(f"🗑️ Deleted reward <strong>{reward['name']}</strong>.", "info")
#     return redirect(url_for("home"))

@app.route("/")
def home():
    db = get_db()

    raw_habits = db.execute("SELECT * FROM habits ORDER BY id DESC").fetchall()
    rewards    = db.execute("SELECT * FROM rewards ORDER BY cost ASC").fetchall()
    player     = db.execute("SELECT * FROM player WHERE id = 1").fetchone()

    habits = []
    for h in raw_habits:
        habits.append({
            "id":                h["id"],
            "name":              h["name"],
            "xp":                h["xp"],
            "streak":            h["streak"],
            "streak_freezes":    h["streak_freezes"],
            "completions_today": completions_today(h["id"]),
        })

    current_level     = player["level"]
    current_xp        = player["total_xp"]
    previous_level_xp = ((current_level - 1) ** 2) * 100
    next_lvl_xp       = xp_for_next_level(current_level)
    progress          = current_xp - previous_level_xp
    needed            = next_lvl_xp - previous_level_xp
    progress_percent  = int((progress / needed) * 100) if needed > 0 else 0

    return render_template(
        "index.html",
        habits=habits,
        rewards=rewards,
        player=player,
        progress_percent=progress_percent,
        next_level_xp=next_lvl_xp,
    )

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True, port=5001)