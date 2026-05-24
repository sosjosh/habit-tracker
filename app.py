from flask import Flask, render_template, request, redirect, url_for, g
import sqlite3
import math
from datetime import datetime, date, timedelta

app = Flask(__name__)
DATABASE = "habits.db"


# ─────────────────────────────────────────────
# DATABASE CONNECTION
# Uses Flask's g object so we open one connection
# per request and close it automatically.
# CHANGED: replaced get_db_connection() with get_db() + teardown
# ─────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")  # NEW: prevents lock errors
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ─────────────────────────────────────────────
# SCHEMA INIT
# CHANGED: removed completions_today column
#          added habit_logs table
# ─────────────────────────────────────────────

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
    # completions_today is GONE — we derive it from habit_logs

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
            id       INTEGER PRIMARY KEY,
            total_xp INTEGER DEFAULT 0,
            level    INTEGER DEFAULT 1
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT    NOT NULL,
            cost INTEGER NOT NULL
        )
    """)

    existing_player = db.execute(
        "SELECT * FROM player WHERE id = 1"
    ).fetchone()

    if not existing_player:
        db.execute(
            "INSERT INTO player (id, total_xp, level) VALUES (1, 0, 1)"
        )

    db.commit()


# ─────────────────────────────────────────────
# LEVEL / XP HELPERS  (unchanged from your version)
# ─────────────────────────────────────────────

def calculate_level(total_xp):
    return max(1, int(math.sqrt(total_xp / 100)) + 1)

def xp_for_next_level(level):
    return (level ** 2) * 100


# ─────────────────────────────────────────────
# DATE-BASED STREAK HELPERS  (NEW)
# ─────────────────────────────────────────────

def get_today():
    return date.today()

def log_completion(habit_id):
    """Write one timestamped entry into habit_logs."""
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
    Streak is alive if the most recent completion was today or yesterday.
    Breaks at the first missing day.
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

    today = get_today()
    streak = 0
    expected = today

    for row in rows:
        day = date.fromisoformat(row["day"])

        if streak == 0 and day < today - timedelta(days=1):
            break  # last completion was 2+ days ago — streak is dead

        if day == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif day < expected:
            break  # gap in calendar — streak ends

    return streak

def completions_today(habit_id):
    """Count log entries for this habit dated today."""
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
# ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def home():
    db = get_db()

    raw_habits = db.execute("SELECT * FROM habits ORDER BY id DESC").fetchall()
    rewards    = db.execute("SELECT * FROM rewards ORDER BY cost ASC").fetchall()
    player     = db.execute("SELECT * FROM player WHERE id = 1").fetchone()

    # NEW: enrich each habit with a live completions_today count
    habits = []
    for h in raw_habits:
        habits.append({
            "id":               h["id"],
            "name":             h["name"],
            "xp":               h["xp"],
            "streak":           h["streak"],
            "completions_today": completions_today(h["id"]),
        })

    current_level    = player["level"]
    current_xp       = player["total_xp"]
    previous_level_xp = ((current_level - 1) ** 2) * 100
    next_lvl_xp      = xp_for_next_level(current_level)
    progress         = current_xp - previous_level_xp
    needed           = next_lvl_xp - previous_level_xp
    progress_percent = int((progress / needed) * 100) if needed > 0 else 0

    return render_template(
        "index.html",
        habits=habits,
        rewards=rewards,
        player=player,
        progress_percent=progress_percent,
        next_level_xp=next_lvl_xp
    )


@app.route("/add_habit", methods=["POST"])
def add_habit():
    name = request.form["name"]
    xp   = request.form["xp"]
    db   = get_db()
    db.execute("INSERT INTO habits (name, xp) VALUES (?, ?)", (name, xp))
    db.commit()
    return redirect(url_for("home"))


@app.route("/complete/<int:habit_id>", methods=["POST"])  # CHANGED: GET → POST
def complete_habit(habit_id):
    db    = get_db()
    habit = db.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()

    if not habit:
        return redirect(url_for("home"))

    # 1. Write the log entry
    log_completion(habit_id)

    # 2. Recalculate streak from logs
    new_streak = calculate_streak(habit_id)
    db.execute("UPDATE habits SET streak = ? WHERE id = ?", (new_streak, habit_id))

    # 3. Award XP and recalculate level
    player   = db.execute("SELECT * FROM player WHERE id = 1").fetchone()
    new_xp   = player["total_xp"] + habit["xp"]
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )

    db.commit()
    return redirect(url_for("home"))


@app.route("/undo_habit/<int:habit_id>", methods=["POST"])  # CHANGED: GET → POST
def undo_habit(habit_id):
    db = get_db()

    # Find the single most recent log entry for this habit
    last_log = db.execute("""
        SELECT id FROM habit_logs
        WHERE habit_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (habit_id,)).fetchone()

    if not last_log:
        return redirect(url_for("home"))  # nothing to undo

    # Delete that log entry
    db.execute("DELETE FROM habit_logs WHERE id = ?", (last_log["id"],))

    # Recalculate streak now that one entry is gone
    new_streak = calculate_streak(habit_id)
    db.execute("UPDATE habits SET streak = ? WHERE id = ?", (new_streak, habit_id))

    # Subtract XP — MAX(0,...) prevents going negative
    habit  = db.execute("SELECT xp FROM habits WHERE id = ?", (habit_id,)).fetchone()
    player = db.execute("SELECT total_xp FROM player WHERE id = 1").fetchone()
    new_xp = max(0, player["total_xp"] - habit["xp"])
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )

    db.commit()
    return redirect(url_for("home"))


@app.route("/delete_habit/<int:habit_id>", methods=["POST"])  # CHANGED: GET → POST
def delete_habit(habit_id):
    db = get_db()
    db.execute("DELETE FROM habit_logs WHERE habit_id = ?", (habit_id,))  # NEW: clean up logs
    db.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
    db.commit()
    return redirect(url_for("home"))


@app.route("/add_reward", methods=["POST"])
def add_reward():
    name = request.form["name"]
    cost = request.form["cost"]
    db   = get_db()
    db.execute("INSERT INTO rewards (name, cost) VALUES (?, ?)", (name, cost))
    db.commit()
    return redirect(url_for("home"))


@app.route("/redeem/<int:reward_id>", methods=["POST"])  # CHANGED: GET → POST
def redeem_reward(reward_id):
    db     = get_db()
    reward = db.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,)).fetchone()
    player = db.execute("SELECT * FROM player WHERE id = 1").fetchone()

    if reward and player["total_xp"] >= reward["cost"]:
        new_xp    = player["total_xp"] - reward["cost"]
        new_level = calculate_level(new_xp)
        db.execute(
            "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
            (new_xp, new_level)
        )
        db.commit()

    return redirect(url_for("home"))


@app.route("/undo_reward/<int:reward_id>", methods=["POST"])  # CHANGED: GET → POST
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

    return redirect(url_for("home"))


@app.route("/delete_reward/<int:reward_id>", methods=["POST"])  # CHANGED: GET → POST
def delete_reward(reward_id):
    db = get_db()
    db.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
    db.commit()
    return redirect(url_for("home"))


# reset_day route is DELETED — no longer needed
# Streaks and daily counts are derived from logs automatically


# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = app  # keeps the app context available for init_db
    with app.app_context():
        init_db()
    app.run(debug=True, port=5001)