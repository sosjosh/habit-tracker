from flask import Flask, render_template, request, redirect, url_for, g, flash, jsonify
import sqlite3
import math
import os
import re
from datetime import datetime, date, timedelta

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

# Railway injects DATABASE_URL; older Heroku-style URLs use postgres:// which
# psycopg2 requires as postgresql://
_DB_URL = os.environ.get("DATABASE_URL", "")
if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)
USE_POSTGRES = bool(_DB_URL and psycopg2)


class PgWrapper:
    """Makes psycopg2 behave like sqlite3 for the patterns used in this app."""

    def __init__(self, conn):
        self._conn = conn
        self._cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.lastrowid = None

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        # SQLite date(timestamp) → Postgres cast
        sql = re.sub(r"\bdate\(timestamp\)", '"timestamp"::date', sql)
        is_insert = sql.strip().upper().startswith("INSERT")
        if is_insert and "RETURNING" not in sql.upper():
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        self._cur.execute(sql, params)
        if is_insert:
            row = self._cur.fetchone()
            self.lastrowid = row["id"] if row else None
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

def is_ajax():
    """Returns True if the request was made via fetch() in app.js."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"

app = Flask(__name__)
app.secret_key = "habitquest-secret-key"
DATABASE = "habits.db"


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def get_db():
    if "db" not in g:
        if USE_POSTGRES:
            g.db = PgWrapper(psycopg2.connect(_DB_URL))
        else:
            conn = sqlite3.connect(DATABASE)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db  = get_db()
    pk  = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS habits (
            id             {pk},
            name           TEXT    NOT NULL,
            xp             INTEGER NOT NULL DEFAULT 10,
            streak         INTEGER NOT NULL DEFAULT 0,
            streak_freezes INTEGER NOT NULL DEFAULT 0,
            sort_order     INTEGER NOT NULL DEFAULT 0,
            pinned         INTEGER NOT NULL DEFAULT 0,
            schedule       TEXT    NOT NULL DEFAULT '1111111'
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id        {pk},
            habit_id  INTEGER NOT NULL,
            timestamp TEXT    NOT NULL,
            note      TEXT    DEFAULT '',
            xp_earned INTEGER DEFAULT 0,
            FOREIGN KEY (habit_id) REFERENCES habits(id)
        )
    """)
    # Patch existing SQLite DBs that pre-date the xp_earned column
    if not USE_POSTGRES:
        try:
            db.execute("ALTER TABLE habit_logs ADD COLUMN xp_earned INTEGER DEFAULT 0")
        except Exception:
            pass

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS freeze_logs (
            id           {pk},
            habit_id     INTEGER NOT NULL,
            habit_log_id INTEGER NOT NULL
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS freeze_spent_logs (
            id           {pk},
            habit_id     INTEGER NOT NULL,
            habit_log_id INTEGER NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS player (
            id       INTEGER PRIMARY KEY,
            total_xp INTEGER DEFAULT 0,
            level    INTEGER DEFAULT 1
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS rewards (
            id   {pk},
            name TEXT    NOT NULL,
            cost INTEGER NOT NULL
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS redemption_logs (
            id          {pk},
            reward_id   INTEGER NOT NULL,
            reward_name TEXT    NOT NULL,
            cost        INTEGER NOT NULL,
            timestamp   TEXT    NOT NULL
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS habit_skips (
            id        {pk},
            habit_id  INTEGER NOT NULL,
            timestamp TEXT    NOT NULL,
            FOREIGN KEY (habit_id) REFERENCES habits(id)
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS todo_lists (
            id         {pk},
            name       TEXT    NOT NULL,
            reward_xp  INTEGER NOT NULL DEFAULT 0,
            completed  INTEGER NOT NULL DEFAULT 0,
            created_at TEXT    NOT NULL
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS todo_items (
            id         {pk},
            list_id    INTEGER NOT NULL,
            text       TEXT    NOT NULL,
            checked    INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (list_id) REFERENCES todo_lists(id)
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
# XP / LEVEL
# ─────────────────────────────────────────────

def calculate_level(total_xp):
    return max(1, int(math.sqrt(total_xp / 100)) + 1)

def xp_for_next_level(level):
    return (level ** 2) * 100

def streak_multiplier(streak):
    return min(2.0, 1.0 + streak * 0.05)


# ─────────────────────────────────────────────
# SCHEDULE HELPER
# ─────────────────────────────────────────────

def is_scheduled_today(schedule):
    """
    schedule is a 7-char string "MTWTFSS".
    Returns True if today's weekday slot is '1'.
    Monday = index 0, Sunday = index 6.
    """
    today_index = date.today().weekday()  # Monday=0, Sunday=6
    if not schedule or len(schedule) != 7:
        return True  # default to always active if malformed
    return schedule[today_index] == '1'

def schedule_display(schedule):
    """Returns a human-readable schedule string like 'Mon Tue Wed'."""
    days  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if not schedule or len(schedule) != 7:
        return "Every day"
    active = [days[i] for i, c in enumerate(schedule) if c == '1']
    if len(active) == 7:
        return "Every day"
    if len(active) == 0:
        return "Never"
    return " · ".join(active)


# ─────────────────────────────────────────────
# STREAK HELPERS
# ─────────────────────────────────────────────

def get_today():
    return date.today()

def get_scheduled_days_in_range(schedule, start_date, end_date):
    """
    Returns a set of date objects between start_date and end_date
    (inclusive) that are scheduled active days.
    """
    scheduled = set()
    current = start_date
    while current <= end_date:
        if is_scheduled_today_for_date(schedule, current):
            scheduled.add(current)
        current += timedelta(days=1)
    return scheduled

def is_scheduled_today_for_date(schedule, d):
    """Same as is_scheduled_today but accepts a specific date."""
    if not schedule or len(schedule) != 7:
        return True
    return schedule[d.weekday()] == '1'

def calculate_streak_only(habit_id):
    """
    Pure streak calc — skips non-scheduled days.
    A Mon-Fri habit does not break on weekends.
    """
    db    = get_db()
    habit = db.execute(
        "SELECT schedule FROM habits WHERE id = ?", (habit_id,)
    ).fetchone()
    schedule = habit["schedule"] if habit else "1111111"

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

    # Wind expected back to the most recent scheduled day
    # (so checking on a non-scheduled day doesn't instantly kill the streak)
    while not is_scheduled_today_for_date(schedule, expected):
        expected -= timedelta(days=1)

    completion_dates = {date.fromisoformat(r["day"]) for r in rows}

    # Fetch skip dates — treated same as completions for streak purposes
    skip_rows = db.execute("""
    SELECT DISTINCT date(timestamp) AS day
    FROM habit_skips
    WHERE habit_id = ?
    """, (habit_id,)).fetchall()
    skip_dates = {date.fromisoformat(r["day"]) for r in skip_rows}

    # Merge: a day counts if completed OR skipped
    valid_dates = completion_dates | skip_dates

    # Walk backwards through scheduled days only
    check = expected
    for _ in range(365):  # safety cap
        if not is_scheduled_today_for_date(schedule, check):
            check -= timedelta(days=1)
            continue
        if check in valid_dates:
            streak += 1
            check -= timedelta(days=1)
        else:
            break  # missed a scheduled day — streak ends

    return streak

def calculate_streak_with_freeze(habit_id, trigger_log_id):
    """
    Streak calc that skips non-scheduled days and auto-spends
    a freeze to bridge a single missed scheduled day.
    """
    db    = get_db()
    habit = db.execute(
        "SELECT schedule, streak_freezes FROM habits WHERE id = ?", (habit_id,)
    ).fetchone()
    schedule = habit["schedule"] if habit else "1111111"

    rows = db.execute("""
        SELECT DISTINCT date(timestamp) AS day
        FROM habit_logs
        WHERE habit_id = ?
        ORDER BY day DESC
    """, (habit_id,)).fetchall()

    if not rows:
        return 0

    today       = get_today()
    streak      = 0
    freeze_used = False

    # Start from most recent scheduled day
    expected = today
    while not is_scheduled_today_for_date(schedule, expected):
        expected -= timedelta(days=1)

    completion_dates = {date.fromisoformat(r["day"]) for r in rows}

    # Fetch skip dates — treated same as completions for streak purposes
    skip_rows = db.execute("""
    SELECT DISTINCT date(timestamp) AS day
    FROM habit_skips
    WHERE habit_id = ?
    """, (habit_id,)).fetchall()
    skip_dates = {date.fromisoformat(r["day"]) for r in skip_rows}

    # Merge: a day counts if completed OR skipped
    valid_dates = completion_dates | skip_dates

    # Don't spend a freeze on the gap before this habit ever started
    min_valid_date = min(valid_dates) if valid_dates else today

    check = expected
    for _ in range(365):
        if not is_scheduled_today_for_date(schedule, check):
            check -= timedelta(days=1)
            continue

        if check in valid_dates:
            streak += 1
            check -= timedelta(days=1)
        elif check < min_valid_date:
            break  # before the habit started — don't spend a freeze here
        elif not freeze_used and habit["streak_freezes"] > 0:
            # Spend freeze to bridge this one missed scheduled day
            db.execute(
                "UPDATE habits SET streak_freezes = streak_freezes - 1 WHERE id = ?",
                (habit_id,)
            )
            db.execute(
                """INSERT INTO freeze_spent_logs (habit_id, habit_log_id)
                   VALUES (?, ?)""",
                (habit_id, trigger_log_id)
            )
            db.commit()
            freeze_used = True
            streak += 1
            check -= timedelta(days=1)
        else:
            break

    return streak

def get_daily_summary():
    """Returns (completed_count, total_scheduled) for today's habits."""
    db        = get_db()
    raw       = db.execute("SELECT id, schedule FROM habits").fetchall()
    today_str = get_today().isoformat()
    total = done = 0
    for h in raw:
        if is_scheduled_today(h["schedule"]):
            total += 1
            cnt = db.execute(
                "SELECT COUNT(*) AS cnt FROM habit_logs WHERE habit_id = ? AND date(timestamp) = ?",
                (h["id"], today_str)
            ).fetchone()["cnt"]
            if cnt > 0:
                done += 1
    return done, total

def completions_today(habit_id):
    db    = get_db()
    today = get_today().isoformat()
    row   = db.execute("""
        SELECT COUNT(*) AS cnt
        FROM habit_logs
        WHERE habit_id = ?
          AND date(timestamp) = ?
    """, (habit_id, today)).fetchone()
    return row["cnt"]

def maybe_award_freeze(habit_id, habit_log_id):
    db = get_db()
    total = db.execute(
        "SELECT COUNT(*) AS cnt FROM habit_logs WHERE habit_id = ?",
        (habit_id,)
    ).fetchone()["cnt"]

    awarded_so_far = db.execute(
        "SELECT COUNT(*) AS cnt FROM freeze_logs WHERE habit_id = ?",
        (habit_id,)
    ).fetchone()["cnt"]

    if total // 5 > awarded_so_far:
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

def get_week_grid(habit_id):
    """Returns a 7-item list for the past 7 days with completion status."""
    db    = get_db()
    today = get_today()

    completed_dates = set()
    rows = db.execute("""
        SELECT DISTINCT date(timestamp) AS day
        FROM habit_logs
        WHERE habit_id = ?
          AND date(timestamp) >= ?
    """, (habit_id, (today - timedelta(days=6)).isoformat())).fetchall()

    for row in rows:
        completed_dates.add(row["day"])

    grid = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        grid.append({
            "date":      d,
            "label":     d.strftime("%a"),
            "today":     d == today,
            "completed": d.isoformat() in completed_dates,
        })
    return grid


# ─────────────────────────────────────────────
# ROUTES — MAIN
# ─────────────────────────────────────────────

@app.route("/")
def home():
    db = get_db()

    # Pinned habits first, then by sort_order
    raw_habits = db.execute("""
        SELECT * FROM habits
        ORDER BY pinned DESC, sort_order ASC
    """).fetchall()

    rewards = db.execute(
        "SELECT * FROM rewards ORDER BY cost ASC"
    ).fetchall()

    player = db.execute(
        "SELECT * FROM player WHERE id = 1"
    ).fetchone()

    today_index     = date.today().weekday()
    total_scheduled = 0
    completed_count = 0

    habits = []
    for h in raw_habits:
        scheduled = is_scheduled_today(h["schedule"])
        ct        = completions_today(h["id"])

        if scheduled:
            total_scheduled += 1
            if ct > 0:
                completed_count += 1

        multiplier = streak_multiplier(h["streak"])
        boosted_xp = int(h["xp"] * multiplier)
        week_grid  = get_week_grid(h["id"])

        habits.append({
            "id":                h["id"],
            "name":              h["name"],
            "xp":                h["xp"],
            "boosted_xp":        boosted_xp,
            "multiplier":        multiplier,
            "streak":            h["streak"],
            "streak_freezes":    h["streak_freezes"],
            "completions_today": ct,
            "pinned":            h["pinned"],
            "sort_order":        h["sort_order"],
            "schedule":          h["schedule"],
            "schedule_display":  schedule_display(h["schedule"]),
            "scheduled_today":   scheduled,
            "week_grid":         week_grid,
        })

    current_level     = player["level"]
    current_xp        = player["total_xp"]
    previous_level_xp = ((current_level - 1) ** 2) * 100
    next_lvl_xp       = xp_for_next_level(current_level)
    progress          = current_xp - previous_level_xp
    needed            = next_lvl_xp - previous_level_xp
    progress_percent  = int((progress / needed) * 100) if needed > 0 else 0

    # Rolling 7-day window headers matching the week_grid order
    week_headers = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        week_headers.append({"label": d.strftime("%a"), "is_today": d == date.today()})

    return render_template(
        "index.html",
        habits=habits,
        rewards=rewards,
        player=player,
        progress_percent=progress_percent,
        next_level_xp=next_lvl_xp,
        total_habits=total_scheduled,
        completed_count=completed_count,
        today_index=today_index,
        week_headers=week_headers,
    )


@app.route("/complete/<int:habit_id>", methods=["POST"])
def complete_habit(habit_id):
    db    = get_db()
    habit = db.execute(
        "SELECT * FROM habits WHERE id = ?", (habit_id,)
    ).fetchone()

    if not habit:
        if is_ajax():
            return jsonify({"ok": False, "message": "Habit not found"}), 404
        return redirect(url_for("home"))

    note = request.form.get("note", "").strip()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate XP ONCE using pre-insert streak, store it on the log
    pre_streak = calculate_streak_only(habit_id)
    multiplier = streak_multiplier(pre_streak)
    earned_xp  = int(habit["xp"] * multiplier)

    cursor = db.execute(
        "INSERT INTO habit_logs (habit_id, timestamp, note, xp_earned) VALUES (?, ?, ?, ?)",
        (habit_id, now, note, earned_xp)
    )
    db.commit()
    new_log_id = cursor.lastrowid

    # Update streak (may spend a freeze) — does NOT change earned_xp
    new_streak = calculate_streak_with_freeze(habit_id, new_log_id)
    db.execute("UPDATE habits SET streak = ? WHERE id = ?", (new_streak, habit_id))

    # Award the already-calculated earned_xp
    player    = db.execute("SELECT * FROM player WHERE id = 1").fetchone()
    new_xp    = player["total_xp"] + earned_xp
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )
    db.commit()

    awarded     = maybe_award_freeze(habit_id, new_log_id)
    completions = completions_today(habit_id)
    bonus_note  = f" (×{multiplier:.2f} streak bonus)" if multiplier > 1 else ""

    if is_ajax():
        messages = []
        if awarded:
            messages.append({
                "category": "freeze",
                "text": f"🧊 Streak freeze earned for {habit['name']}!"
            })
        messages.append({
            "category": "success",
            "text": f"✅ Completed {habit['name']} — +{earned_xp} XP!{bonus_note}"
        })

        current_level    = new_level
        prev_xp          = ((current_level - 1) ** 2) * 100
        next_xp          = (current_level ** 2) * 100
        needed           = next_xp - prev_xp
        progress_percent = int(((new_xp - prev_xp) / needed) * 100) if needed > 0 else 0

        done_count, total_count = get_daily_summary()

        return jsonify({
            "ok":                True,
            "messages":          messages,
            "completions_today": completions,
            "streak":            new_streak,
            "total_xp":          new_xp,
            "level":             new_level,
            "earned_xp":         earned_xp,
            "multiplier":        multiplier,
            "boosted_xp":        int(habit["xp"] * multiplier),
            "streak_freezes":    db.execute(
                "SELECT streak_freezes FROM habits WHERE id = ?", (habit_id,)
            ).fetchone()["streak_freezes"],
            "progress_percent":  progress_percent,
            "next_level_xp":     next_xp,
            "completed_count":   done_count,
            "total_habits":      total_count,
        })

    if awarded:
        flash(f"🧊 Streak freeze earned for <strong>{habit['name']}</strong>!", "freeze")
    flash(
        f"✅ Completed <strong>{habit['name']}</strong> — +{earned_xp} XP!{bonus_note}",
        "success"
    )
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
        if is_ajax():
            return jsonify({"ok": False, "message": "Nothing to undo."})
        flash("Nothing to undo.", "info")
        return redirect(url_for("home"))

    log_id = last_log["id"]

    # Read the exact XP that was awarded at completion time
    log_row   = db.execute(
        "SELECT xp_earned FROM habit_logs WHERE id = ?", (log_id,)
    ).fetchone()
    earned_xp = log_row["xp_earned"] if log_row and log_row["xp_earned"] else 0

    freeze_award = db.execute(
        "SELECT id FROM freeze_logs WHERE habit_log_id = ?", (log_id,)
    ).fetchone()
    if freeze_award:
        db.execute("DELETE FROM freeze_logs WHERE id = ?", (freeze_award["id"],))
        db.execute(
            "UPDATE habits SET streak_freezes = MAX(0, streak_freezes - 1) WHERE id = ?",
            (habit_id,)
        )

    freeze_spend = db.execute(
        "SELECT id FROM freeze_spent_logs WHERE habit_log_id = ?", (log_id,)
    ).fetchone()
    if freeze_spend:
        db.execute(
            "DELETE FROM freeze_spent_logs WHERE id = ?", (freeze_spend["id"],)
        )
        db.execute(
            "UPDATE habits SET streak_freezes = streak_freezes + 1 WHERE id = ?",
            (habit_id,)
        )

    db.execute("DELETE FROM habit_logs WHERE id = ?", (log_id,))
    

    new_streak = calculate_streak_only(habit_id)
    habit      = db.execute(
        "SELECT * FROM habits WHERE id = ?", (habit_id,)
    ).fetchone()
    db.execute(
        "UPDATE habits SET streak = ? WHERE id = ?", (new_streak, habit_id)
    )

    # Use stored earned_xp instead of recalculating
    player    = db.execute("SELECT total_xp FROM player WHERE id = 1").fetchone()
    new_xp    = max(0, player["total_xp"] - earned_xp)
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )
    db.commit()

    completions = completions_today(habit_id)

    if is_ajax():

        # Recalculate after the update
        current_level    = new_level
        prev_xp          = ((current_level - 1) ** 2) * 100
        next_xp          = (current_level ** 2) * 100
        needed           = next_xp - prev_xp
        progress         = new_xp - prev_xp
        progress_percent = int((progress / needed) * 100) if needed > 0 else 0
        undo_multiplier  = streak_multiplier(new_streak)
        done_count, total_count = get_daily_summary()

        return jsonify({
            "ok":                True,
            "messages":          [{"category": "info",
                                "text": f"↩️ Undid {habit['name']} — -{earned_xp} XP."}],
            "completions_today": completions,
            "streak":            new_streak,
            "total_xp":          new_xp,
            "level":             new_level,
            "streak_freezes":    habit["streak_freezes"],
            "progress_percent":  progress_percent,
            "next_level_xp":     next_xp,
            "multiplier":        undo_multiplier,
            "boosted_xp":        int(habit["xp"] * undo_multiplier),
            "completed_count":   done_count,
            "total_habits":      total_count,
        })


    flash(f"↩️ Undid <strong>{habit['name']}</strong> — -{earned_xp} XP.", "info")
    return redirect(url_for("home"))


@app.route("/pin/<int:habit_id>", methods=["POST"])
def pin_habit(habit_id):
    db    = get_db()
    habit = db.execute(
        "SELECT pinned FROM habits WHERE id = ?", (habit_id,)
    ).fetchone()
    if not habit:
        if is_ajax(): return jsonify({"ok": False})
        return redirect(url_for("home"))

    new_pinned = 0 if habit["pinned"] else 1
    db.execute(
        "UPDATE habits SET pinned = ? WHERE id = ?", (new_pinned, habit_id)
    )
    db.commit()

    if is_ajax():
        return jsonify({"ok": True, "pinned": new_pinned})
    return redirect(url_for("home"))


@app.route("/reorder", methods=["POST"])
def reorder_habits():
    """
    Receives a comma-separated list of habit ids in the new order.
    Called by drag-and-drop in app.js.
    """
    db       = get_db()
    order    = request.form.get("order", "")
    habit_ids = [int(x) for x in order.split(",") if x.strip().isdigit()]

    for i, habit_id in enumerate(habit_ids):
        db.execute(
            "UPDATE habits SET sort_order = ? WHERE id = ?",
            (i, habit_id)
        )
    db.commit()
    return "", 204  # no content — JS handles the response


@app.route("/add_note/<int:habit_id>", methods=["POST"])
def add_note(habit_id):
    """Add or update a note on the most recent log entry for this habit."""
    db   = get_db()
    note = request.form.get("note", "").strip()

    last_log = db.execute("""
        SELECT id FROM habit_logs
        WHERE habit_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (habit_id,)).fetchone()

    if not last_log:
        flash("No completion to add a note to.", "info")
        return redirect(url_for("habit_history", habit_id=habit_id))

    db.execute(
        "UPDATE habit_logs SET note = ? WHERE id = ?",
        (note, last_log["id"])
    )
    db.commit()
    flash("📝 Note saved.", "success")
    return redirect(url_for("habit_history", habit_id=habit_id))

@app.route("/skip/<int:habit_id>", methods=["POST"])
def skip_habit(habit_id):
    """
    Mark today as an intentional skip for this habit.
    Inserts a skip log so the streak calculator knows
    this day was deliberate, not a miss.
    Streak is preserved without spending a freeze.
    """
    db    = get_db()
    habit = db.execute(
        "SELECT * FROM habits WHERE id = ?", (habit_id,)
    ).fetchone()

    if not habit:
        if is_ajax(): return jsonify({"ok": False})
        return redirect(url_for("home"))

    today = get_today().isoformat()
    already_skipped = db.execute("""
        SELECT id FROM habit_skips
        WHERE habit_id = ? AND date(timestamp) = ?
    """, (habit_id, today)).fetchone()

    if already_skipped:
        if is_ajax():
            return jsonify({
                "ok": False,
                "messages": [{"category": "info",
                              "text": f"Already skipped {habit['name']} today."}]
            })
        flash(f"Already skipped <strong>{habit['name']}</strong> today.", "info")
        return redirect(url_for("home"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO habit_skips (habit_id, timestamp) VALUES (?, ?)",
        (habit_id, now)
    )
    db.commit()

    if is_ajax():
        return jsonify({
            "ok": True,
            "messages": [{"category": "info",
                          "text": f"⏭️ Skipped {habit['name']} — streak preserved."}]
        })
    flash(
        f"⏭️ Skipped <strong>{habit['name']}</strong> today — streak preserved.",
        "info"
    )
    return redirect(url_for("home"))


# ─────────────────────────────────────────────
# ROUTES — ADMIN
# ─────────────────────────────────────────────

@app.route("/admin")
def admin():
    db      = get_db()
    habits  = db.execute("SELECT * FROM habits ORDER BY sort_order ASC").fetchall()
    rewards = db.execute("SELECT * FROM rewards ORDER BY cost ASC").fetchall()
    return render_template("admin.html", habits=habits, rewards=rewards)


@app.route("/admin/add_habit", methods=["POST"])
def admin_add_habit():
    db       = get_db()
    name     = request.form.get("name", "").strip()
    xp       = int(request.form.get("xp", 10))
    days     = request.form.getlist("days")
    schedule = "".join("1" if str(i) in days else "0" for i in range(7))
    if not name:
        flash("Habit name required.", "error")
        return redirect(url_for("admin"))
    max_order = db.execute("SELECT COALESCE(MAX(sort_order),0) AS m FROM habits").fetchone()["m"]
    db.execute(
        "INSERT INTO habits (name, xp, schedule, sort_order) VALUES (?, ?, ?, ?)",
        (name, xp, schedule, max_order + 1)
    )
    db.commit()
    flash(f"✅ Added habit <strong>{name}</strong>.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/edit_habit/<int:habit_id>", methods=["POST"])
def admin_edit_habit(habit_id):
    db       = get_db()
    name     = request.form.get("name", "").strip()
    xp       = int(request.form.get("xp", 10))
    days     = request.form.getlist("days")
    schedule = "".join("1" if str(i) in days else "0" for i in range(7))
    if not name:
        flash("Habit name required.", "error")
        return redirect(url_for("admin"))
    db.execute(
        "UPDATE habits SET name = ?, xp = ?, schedule = ? WHERE id = ?",
        (name, xp, schedule, habit_id)
    )
    db.commit()
    flash(f"✏️ Updated <strong>{name}</strong>.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/delete_habit/<int:habit_id>", methods=["POST"])
def admin_delete_habit(habit_id):
    db    = get_db()
    habit = db.execute("SELECT name FROM habits WHERE id = ?", (habit_id,)).fetchone()
    db.execute("DELETE FROM habit_logs      WHERE habit_id = ?", (habit_id,))
    db.execute("DELETE FROM habit_skips     WHERE habit_id = ?", (habit_id,))
    db.execute("DELETE FROM freeze_logs     WHERE habit_id = ?", (habit_id,))
    db.execute("DELETE FROM freeze_spent_logs WHERE habit_id = ?", (habit_id,))
    db.execute("DELETE FROM habits          WHERE id = ?",        (habit_id,))
    db.commit()
    flash(f"🗑️ Deleted <strong>{habit['name']}</strong>.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/add_reward", methods=["POST"])
def admin_add_reward():
    db   = get_db()
    name = request.form.get("name", "").strip()
    cost = int(request.form.get("cost", 100))
    if not name:
        flash("Reward name required.", "error")
        return redirect(url_for("admin"))
    db.execute("INSERT INTO rewards (name, cost) VALUES (?, ?)", (name, cost))
    db.commit()
    flash(f"🎁 Added reward <strong>{name}</strong>.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/edit_reward/<int:reward_id>", methods=["POST"])
def admin_edit_reward(reward_id):
    db   = get_db()
    name = request.form.get("name", "").strip()
    cost = int(request.form.get("cost", 100))
    db.execute("UPDATE rewards SET name = ?, cost = ? WHERE id = ?", (name, cost, reward_id))
    db.commit()
    flash(f"✏️ Updated <strong>{name}</strong>.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/delete_reward/<int:reward_id>", methods=["POST"])
def admin_delete_reward(reward_id):
    db     = get_db()
    reward = db.execute("SELECT name FROM rewards WHERE id = ?", (reward_id,)).fetchone()
    db.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
    db.commit()
    flash(f"🗑️ Deleted <strong>{reward['name']}</strong>.", "info")
    return redirect(url_for("admin"))


# ─────────────────────────────────────────────
# ROUTES — REWARDS
# ─────────────────────────────────────────────

@app.route("/redeem/<int:reward_id>", methods=["POST"])
def redeem_reward(reward_id):
    db     = get_db()
    reward = db.execute(
        "SELECT * FROM rewards WHERE id = ?", (reward_id,)
    ).fetchone()
    player = db.execute(
        "SELECT * FROM player WHERE id = 1"
    ).fetchone()

    if not reward:
        return redirect(url_for("home"))

    if player["total_xp"] < reward["cost"]:
        flash(
            f"❌ Not enough XP for <strong>{reward['name']}</strong>. "
            f"Need {reward['cost']} XP.",
            "error"
        )
        return redirect(url_for("home"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """INSERT INTO redemption_logs
           (reward_id, reward_name, cost, timestamp)
           VALUES (?, ?, ?, ?)""",
        (reward["id"], reward["name"], reward["cost"], now)
    )

    new_xp    = player["total_xp"] - reward["cost"]
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )
    db.commit()

    flash(
        f"🎁 Redeemed <strong>{reward['name']}</strong> for {reward['cost']} XP!",
        "success"
    )
    return redirect(url_for("home"))


@app.route("/undo_reward/<int:reward_id>", methods=["POST"])
def undo_reward(reward_id):
    db     = get_db()
    reward = db.execute(
        "SELECT * FROM rewards WHERE id = ?", (reward_id,)
    ).fetchone()
    player = db.execute(
        "SELECT * FROM player WHERE id = 1"
    ).fetchone()

    if not reward:
        return redirect(url_for("home"))

    # Only undo if there is actually a redemption log entry for this reward
    last_redemption = db.execute("""
        SELECT id FROM redemption_logs
        WHERE reward_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (reward_id,)).fetchone()

    if not last_redemption:
        flash(
            f"❌ No purchase record found for "
            f"<strong>{reward['name']}</strong> — nothing to undo.",
            "error"
        )
        return redirect(url_for("home"))

    db.execute(
        "DELETE FROM redemption_logs WHERE id = ?",
        (last_redemption["id"],)
    )

    new_xp    = player["total_xp"] + reward["cost"]
    new_level = calculate_level(new_xp)
    db.execute(
        "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
        (new_xp, new_level)
    )
    db.commit()

    flash(
        f"↩️ Undid redemption of <strong>{reward['name']}</strong> — "
        f"+{reward['cost']} XP returned.",
        "info"
    )
    return redirect(url_for("home"))


@app.route("/inventory")
def inventory():
    db   = get_db()
    logs = db.execute("""
        SELECT reward_name, cost, timestamp
        FROM redemption_logs
        ORDER BY timestamp DESC
    """).fetchall()
    return render_template("inventory.html", logs=logs)


# ─────────────────────────────────────────────
# ROUTES — HABIT HISTORY
# ─────────────────────────────────────────────

@app.route("/habit/<int:habit_id>/history")
def habit_history(habit_id):
    db    = get_db()
    habit = db.execute(
        "SELECT * FROM habits WHERE id = ?", (habit_id,)
    ).fetchone()

    if not habit:
        return redirect(url_for("home"))

    logs = db.execute("""
        SELECT id, timestamp, note
        FROM habit_logs
        WHERE habit_id = ?
        ORDER BY timestamp DESC
    """, (habit_id,)).fetchall()

    today     = get_today()
    week_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]

    completed_dates = set()
    for row in logs:
        completed_dates.add(row["timestamp"][:10])

    week_grid = []
    for d in week_days:
        week_grid.append({
            "date":      d,
            "label":     d.strftime("%a"),
            "completed": d.isoformat() in completed_dates,
        })

    return render_template(
        "history.html",
        habit=habit,
        logs=logs,
        week_grid=week_grid,
        schedule_display=schedule_display(habit["schedule"]),
    )

# ─────────────────────────────────────────────
# ROUTES — TODO LISTS
# ─────────────────────────────────────────────

@app.route("/todos")
def todos():
    db    = get_db()
    lists = db.execute("""
        SELECT * FROM todo_lists ORDER BY completed ASC, id DESC
    """).fetchall()

    player = db.execute("SELECT * FROM player WHERE id = 1").fetchone()

    # Attach items to each list
    todo_data = []
    for lst in lists:
        items = db.execute("""
            SELECT * FROM todo_items
            WHERE list_id = ?
            ORDER BY sort_order ASC, id ASC
        """, (lst["id"],)).fetchall()

        total   = len(items)
        checked = sum(1 for i in items if i["checked"])

        todo_data.append({
            "id":        lst["id"],
            "name":      lst["name"],
            "reward_xp": lst["reward_xp"],
            "completed": lst["completed"],
            "todo_items":     items,
            "total":     total,
            "checked":   checked,
            "percent":   int((checked / total) * 100) if total > 0 else 0,
        })

    return render_template("todos.html", todo_data=todo_data, player=player)


@app.route("/todos/add_list", methods=["POST"])
def add_todo_list():
    db        = get_db()
    name      = request.form.get("name", "").strip()
    reward_xp = int(request.form.get("reward_xp", 0))
    now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not name:
        flash("List name cannot be empty.", "error")
        return redirect(url_for("todos"))

    db.execute(
        "INSERT INTO todo_lists (name, reward_xp, created_at) VALUES (?, ?, ?)",
        (name, reward_xp, now)
    )
    db.commit()
    flash(f"📋 Created list <strong>{name}</strong>.", "success")
    return redirect(url_for("todos"))


@app.route("/todos/<int:list_id>/add_item", methods=["POST"])
def add_todo_item(list_id):
    db   = get_db()
    text = request.form.get("text", "").strip()

    if not text:
        flash("Item text cannot be empty.", "error")
        return redirect(url_for("todos"))

    max_order = db.execute(
        "SELECT MAX(sort_order) AS m FROM todo_items WHERE list_id = ?",
        (list_id,)
    ).fetchone()["m"] or 0

    db.execute(
        "INSERT INTO todo_items (list_id, text, sort_order) VALUES (?, ?, ?)",
        (list_id, text, max_order + 1)
    )
    db.commit()
    return redirect(url_for("todos"))


@app.route("/todos/<int:list_id>/check/<int:item_id>", methods=["POST"])
def check_todo_item(list_id, item_id):
    db   = get_db()
    item = db.execute(
        "SELECT * FROM todo_items WHERE id = ?", (item_id,)
    ).fetchone()

    if not item:
        return redirect(url_for("todos"))

    # Toggle checked state
    new_checked = 0 if item["checked"] else 1
    db.execute(
        "UPDATE todo_items SET checked = ? WHERE id = ?",
        (new_checked, item_id)
    )
    db.commit()

    # Check if all items in this list are now complete
    lst = db.execute(
        "SELECT * FROM todo_lists WHERE id = ?", (list_id,)
    ).fetchone()

    total   = db.execute(
        "SELECT COUNT(*) AS cnt FROM todo_items WHERE list_id = ?",
        (list_id,)
    ).fetchone()["cnt"]

    checked = db.execute(
        "SELECT COUNT(*) AS cnt FROM todo_items WHERE list_id = ? AND checked = 1",
        (list_id,)
    ).fetchone()["cnt"]

    # Award XP if just became fully complete and wasn't already marked complete
    if total > 0 and checked == total and not lst["completed"]:
        db.execute(
            "UPDATE todo_lists SET completed = 1 WHERE id = ?", (list_id,)
        )

        if lst["reward_xp"] > 0:
            player    = db.execute("SELECT * FROM player WHERE id = 1").fetchone()
            new_xp    = player["total_xp"] + lst["reward_xp"]
            new_level = calculate_level(new_xp)
            db.execute(
                "UPDATE player SET total_xp = ?, level = ? WHERE id = 1",
                (new_xp, new_level)
            )
            db.commit()
            flash(
                f"🏆 Completed <strong>{lst['name']}</strong>! "
                f"+{lst['reward_xp']} XP awarded!",
                "success"
            )
        else:
            flash(
                f"✅ Completed <strong>{lst['name']}</strong>!",
                "success"
            )

    # If unchecking an item on a completed list, reopen it
    elif lst["completed"] and new_checked == 0:
        db.execute(
            "UPDATE todo_lists SET completed = 0 WHERE id = ?", (list_id,)
        )
        db.commit()

    db.commit()
    return redirect(url_for("todos"))


@app.route("/todos/<int:list_id>/delete", methods=["POST"])
def delete_todo_list(list_id):
    db  = get_db()
    lst = db.execute(
        "SELECT name FROM todo_lists WHERE id = ?", (list_id,)
    ).fetchone()
    db.execute("DELETE FROM todo_items WHERE list_id = ?", (list_id,))
    db.execute("DELETE FROM todo_lists WHERE id = ?",      (list_id,))
    db.commit()
    flash(f"🗑️ Deleted list <strong>{lst['name']}</strong>.", "info")
    return redirect(url_for("todos"))


@app.route("/todos/<int:list_id>/delete_item/<int:item_id>", methods=["POST"])
def delete_todo_item(list_id, item_id):
    db = get_db()

    # If deleting from a completed list, reopen it
    # (total items changed so completion is no longer valid)
    lst = db.execute(
        "SELECT * FROM todo_lists WHERE id = ?", (list_id,)
    ).fetchone()
    if lst and lst["completed"]:
        db.execute(
            "UPDATE todo_lists SET completed = 0 WHERE id = ?", (list_id,)
        )

    db.execute("DELETE FROM todo_items WHERE id = ?", (item_id,))
    db.commit()
    return redirect(url_for("todos"))


@app.route("/todos/<int:list_id>/reset", methods=["POST"])
def reset_todo_list(list_id):
    """Uncheck all items and reopen the list so it can be reused."""
    db = get_db()
    db.execute(
        "UPDATE todo_items SET checked = 0 WHERE list_id = ?", (list_id,)
    )
    db.execute(
        "UPDATE todo_lists SET completed = 0 WHERE id = ?", (list_id,)
    )
    db.commit()
    flash("🔄 List reset.", "info")
    return redirect(url_for("todos"))

# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────

# Run on every startup (gunicorn imports this module, so __main__ is skipped)
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)