import sqlite3
from datetime import date
def get_cursor():
    "Get a cursor for the database connection."
    connection = sqlite3.connect("gym_tracker.db")
    cursor = connection.cursor()
    return connection, cursor

def add_exercise(name):
    "Add a new exercise to the database. Arguments: name (str): The name of the exercise to add."
    connection, cursor = get_cursor()
    cursor.execute("INSERT INTO exercises (name) VALUES (?)", (name,))
    connection.commit()

def view_exercises():
    "Retrieve all exercises in the database. Returns list of (id, name) tuples."
    connection, cursor = get_cursor()
    cursor.execute("SELECT * FROM exercises")
    exercises = cursor.fetchall()
    return exercises
def log_set(exercise_id, weight, reps, today):
    """log a new set for an exercise. 
    Args: exercise_id (int): The ID of the exercise. weight (float): The weight used. 
    reps (int): The number of repetitions. today (str): The date of the set."""
    connection, cursor = get_cursor()
    today = str(date.today())
    cursor.execute("INSERT INTO sets (exercise_id, weight, reps, date) VALUES (?, ?, ?, ?)", (exercise_id, weight, reps, today))
    connection.commit()


print("1. Add an exercise \n2. View exercises \n3. Log a set")
choice = input("Choose an option: ")

if choice == "1":
    name = input("Enter exercise name: ")
    add_exercise(name)
elif choice == "2":
    print(view_exercises())
elif choice == "3":
    exercise_id = int(input("Enter exercise ID: "))
    weight = float(input("Enter weight: "))
    reps = int(input("Enter number of reps: "))
    log_set(exercise_id, weight, reps, str(date.today()))