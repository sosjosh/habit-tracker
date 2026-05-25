# data.py
# Define your habits and rewards here.
# Run:  python seed.py   to load them into the database.
# Adding new items: add them here, re-run seed.py.

HABITS = [
    {"name": "Lift",                "xp": 50},
    {"name": "Read 20 Minutes",     "xp": 20},
    {"name": "Drink 1 Gallon",      "xp": 25},
    {"name": "Out of Bed @ 7AM",    "xp": 20},
    {"name": "Hit 100g Protein",    "xp": 30},
    {"name": "Brush/Floss",         "xp": 5},
]

REWARDS = [
    {"name": "10 Min Screen Unlock",    "cost": 20},
    {"name": "Grub",                    "cost": 100},
    {"name": "New Record",              "cost": 150},
]