from flask import Flask, render_template, request, redirect
import sqlite3
from datetime import datetime

app = Flask(__name__)

DATABASE = "habits.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            xp INTEGER NOT NULL,
            streak INTEGER DEFAULT 0,
            completed_today INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player (
            id INTEGER PRIMARY KEY,
            total_xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cost INTEGER NOT NULL
        )
        """
    )

    existing_player = cursor.execute(
        "SELECT * FROM player WHERE id = 1"
    ).fetchone()

    if not existing_player:
        cursor.execute(
            "INSERT INTO player (id, total_xp, level) VALUES (1, 0, 1)"
        )

    conn.commit()
    conn.close()


def calculate_level(total_xp):
    return max(1, int((total_xp / 100) ** 0.5) + 1)


@app.route("/")
def home():
    conn = get_db_connection()

    habits = conn.execute(
        "SELECT * FROM habits ORDER BY id DESC"
    ).fetchall()

    rewards = conn.execute(
        "SELECT * FROM rewards ORDER BY cost ASC"
    ).fetchall()

    player = conn.execute(
        "SELECT * FROM player WHERE id = 1"
    ).fetchone()

    conn.close()

    return render_template(
        "index.html",
        habits=habits,
        rewards=rewards,
        player=player
    )


@app.route("/add_habit", methods=["POST"])
def add_habit():
    name = request.form["name"]
    xp = request.form["xp"]

    conn = get_db_connection()

    conn.execute(
        "INSERT INTO habits (name, xp) VALUES (?, ?)",
        (name, xp)
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/complete/<int:habit_id>")
def complete_habit(habit_id):
    conn = get_db_connection()

    habit = conn.execute(
        "SELECT * FROM habits WHERE id = ?",
        (habit_id,)
    ).fetchone()

    if habit and habit["completed_today"] == 0:
        new_streak = habit["streak"] + 1

        conn.execute(
            """
            UPDATE habits
            SET completed_today = 1,
                streak = ?
            WHERE id = ?
            """,
            (new_streak, habit_id)
        )

        player = conn.execute(
            "SELECT * FROM player WHERE id = 1"
        ).fetchone()

        total_xp = player["total_xp"] + habit["xp"]
        level = calculate_level(total_xp)

        conn.execute(
            """
            UPDATE player
            SET total_xp = ?,
                level = ?
            WHERE id = 1
            """,
            (total_xp, level)
        )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/reset_day")
def reset_day():
    conn = get_db_connection()

    conn.execute(
        "UPDATE habits SET completed_today = 0"
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/add_reward", methods=["POST"])
def add_reward():
    name = request.form["name"]
    cost = request.form["cost"]

    conn = get_db_connection()

    conn.execute(
        "INSERT INTO rewards (name, cost) VALUES (?, ?)",
        (name, cost)
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/redeem/<int:reward_id>")
def redeem_reward(reward_id):
    conn = get_db_connection()

    reward = conn.execute(
        "SELECT * FROM rewards WHERE id = ?",
        (reward_id,)
    ).fetchone()

    player = conn.execute(
        "SELECT * FROM player WHERE id = 1"
    ).fetchone()

    if reward and player["total_xp"] >= reward["cost"]:
        new_xp = player["total_xp"] - reward["cost"]
        new_level = calculate_level(new_xp)

        conn.execute(
            """
            UPDATE player
            SET total_xp = ?,
                level = ?
            WHERE id = 1
            """,
            (new_xp, new_level)
        )

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/delete_habit/<int:habit_id>")
def delete_habit(habit_id):
    conn = get_db_connection()

    conn.execute(
        "DELETE FROM habits WHERE id = ?",
        (habit_id,)
    )

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/delete_reward/<int:reward_id>")
def delete_reward(reward_id):
    conn = get_db_connection()

    conn.execute(
        "DELETE FROM rewards WHERE id = ?",
        (reward_id,)
    )

    conn.commit()
    conn.close()

    return redirect("/")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)