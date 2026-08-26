import sqlite3
connection = sqlite3.connect("gym_tracker.db")
cursor = connection.cursor()
cursor.execute("""
    CREATE TABLE sets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exercise_id INTEGER NOT NULL,
        weight REAL NOT NULL,
        reps INTEGER NOT NULL,
        date TEXT NOT NULL
    )
""")
cursor.execute("""
    CREATE TABLE exercises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    )
    """)
connection.commit()