# data.py
# Define your habits and rewards here.
# Run:  python seed.py   to load them into the database.
# Adding new items: add them here, re-run seed.py.

HABITS = [
    {"name": "Lift",                "xp": 50, "pinned": 0, "schedule": "1111111"},
    {"name": "Read 20 Minutes",     "xp": 20, "pinned": 0, "schedule": "1111111"},
    {"name": "Drink 1 Gallon",      "xp": 25, "pinned": 0, "schedule": "1111111"},
    {"name": "Out of Bed @ 7AM",    "xp": 20, "pinned": 1, "schedule": "1111100"},
    {"name": "Hit 100g Protein",    "xp": 30, "pinned": 0, "schedule": "1111111"},
    {"name": "Brush/Floss",         "xp": 5, "pinned": 1, "schedule": "1111111"},
]

REWARDS = [
    {"name": "30 Min Scroll",           "cost": 20},
    {"name": "10 Min Screen Unlock",    "cost": 20},
    {"name": "Nice Solo Meal Out",      "cost": 150},
    {"name": "New Record",              "cost": 100},
]