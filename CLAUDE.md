# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python3 app.py          # starts on http://localhost:5001 in debug mode
```

## Database Setup

On a **fresh database**, run these in order after starting the app once (which calls `init_db()`):

```bash
python3 migrate/migrate7.py   # creates todo_lists and todo_items tables
python3 migrate8.py           # adds xp_earned column to habit_logs
```

To seed or update habits and rewards:

```bash
python3 seed.py   # idempotent — inserts new, updates existing by name
```

Habits and rewards are defined in `data.py`. Edit that file and re-run `seed.py` to add or change them.

## Architecture

This is a single-file Flask app (`app.py`) backed by a SQLite database (`habits.db`, WAL mode). There is no ORM — all queries are raw SQL via `sqlite3`. Templates are Jinja2 (`templates/`), with vanilla JS in `static/app.js`.

### Request Handling Pattern

Every mutating route (`/complete`, `/undo_habit`, `/skip`, `/pin`) serves **both** a normal HTML form submission and an AJAX fetch from `app.js`. The `is_ajax()` helper checks for the `X-Requested-With: XMLHttpRequest` header:
- AJAX → return `jsonify(...)` with updated state
- Normal → `flash(...)` + `redirect(url_for("home"))`

`app.js` uses `postForm()` to send all mutations as AJAX, then calls `updateHabitCard()` to patch the DOM in place without a full page reload.

### Streak Logic

Two streak functions in `app.py`:

- `calculate_streak_only(habit_id)` — pure read, no side effects. Skips non-scheduled days (so a Mon–Fri habit doesn't break on weekends). Both completions (`habit_logs`) and intentional skips (`habit_skips`) count as "valid" days.
- `calculate_streak_with_freeze(habit_id, trigger_log_id)` — called at completion time. Same logic, but auto-spends one streak freeze to bridge a single missed scheduled day, writing to `freeze_spent_logs` and decrementing `habits.streak_freezes`.

Freezes are awarded every 5 completions (tracked in `freeze_logs`). Undo reverses both the freeze award and any freeze that was spent.

### Schedule Format

`habits.schedule` is a 7-character string (e.g. `"1111100"`), where index 0 = Monday, index 6 = Sunday. `'1'` means the habit is active that day. `"1111111"` = every day.

### XP and Levels

- Level formula: `max(1, int(sqrt(total_xp / 100)) + 1)`
- XP needed for next level: `level² × 100`
- Streak multiplier: `min(2.0, 1.0 + streak × 0.05)` — caps at 2× at a 20-day streak
- Earned XP is calculated **before** inserting the log (using pre-completion streak), then stored on `habit_logs.xp_earned`. Undo reads this stored value rather than recalculating, so the subtraction is always exact.

### Database Schema (key tables)

| Table | Purpose |
|---|---|
| `habits` | Habit definitions with schedule, XP, streak, freezes, pin, sort order |
| `habit_logs` | One row per completion; includes `xp_earned` (added by migrate8) |
| `habit_skips` | Intentional skips — treated same as completions for streak |
| `freeze_logs` | Records when a freeze was awarded (1 per 5 completions) |
| `freeze_spent_logs` | Records when a freeze was auto-spent to bridge a missed day |
| `player` | Single row (id=1): `total_xp`, `level` |
| `rewards` | Redeemable rewards with XP cost |
| `redemption_logs` | Reward purchase history (used for undo) |
| `todo_lists` | Named to-do lists with optional XP reward on completion |
| `todo_items` | Items within a list; list auto-completes when all items checked |

### Migration Pattern

Schema changes live in numbered `migrate/migrate*.py` scripts (plus `migrate8.py` at root). Each is meant to be run once manually. `init_db()` only creates the original core tables — tables added later (`todo_lists`, `todo_items`, `habit_logs.xp_earned`) require the corresponding migration scripts.