"""HTTP API for exercises and dated sets. Run with uvicorn api:app --reload."""

import sqlite3
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from progress_photos import create_router, PhotoPrivacyMiddleware

DB_PATH = Path(__file__).resolve().parent / "gym_tracker.db"
app = FastAPI(title="Gym Tracker API")


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


class ExerciseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Exercise name cannot be blank")
        return value


class SetValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weight: float = Field(gt=0, allow_inf_nan=False)
    reps: int = Field(gt=0, strict=True)


class SetInput(SetValues):
    exercise_id: int = Field(gt=0)


def require_exercise(db, exercise_id):
    row = db.execute("SELECT id, name FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Exercise not found")
    return dict(row)


def require_set(db, set_id):
    row = db.execute("SELECT id, exercise_id, weight, reps, date FROM sets WHERE id = ?", (set_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Set not found")
    return dict(row)


@app.get("/exercises")
def list_exercises(db=Depends(get_db)):
    return [dict(row) for row in db.execute("SELECT id, name FROM exercises ORDER BY id")]


@app.post("/exercises", status_code=201)
def create_exercise(body: ExerciseInput, db=Depends(get_db)):
    # Serialize the application-level duplicate check and insert without a schema change.
    with db:
        db.execute("BEGIN IMMEDIATE")
        names = db.execute("SELECT name FROM exercises").fetchall()
        if any(row["name"].strip().casefold() == body.name.casefold() for row in names):
            raise HTTPException(409, "Exercise name already exists")
        cursor = db.execute("INSERT INTO exercises (name) VALUES (?)", (body.name,))
        return {"id": cursor.lastrowid, "name": body.name}


@app.get("/exercises/{exercise_id}/last-set")
def last_set(exercise_id: int, db=Depends(get_db)):
    require_exercise(db, exercise_id)
    row = db.execute(
        "SELECT id, exercise_id, weight, reps, date FROM sets "
        "WHERE exercise_id = ? ORDER BY id DESC LIMIT 1", (exercise_id,)
    ).fetchone()
    return dict(row) if row else None


@app.get("/sets")
def list_sets(exercise_id: int | None = None, db=Depends(get_db)):
    if exercise_id is not None:
        require_exercise(db, exercise_id)
        rows = db.execute("SELECT * FROM sets WHERE exercise_id = ? ORDER BY id DESC", (exercise_id,))
    else:
        rows = db.execute("SELECT * FROM sets ORDER BY id DESC")
    return [dict(row) for row in rows]


@app.post("/sets", status_code=201)
def create_set(body: SetInput, db=Depends(get_db)):
    require_exercise(db, body.exercise_id)
    with db:
        cursor = db.execute(
            "INSERT INTO sets (exercise_id, weight, reps, date) VALUES (?, ?, ?, ?)",
            (body.exercise_id, body.weight, body.reps, date.today().isoformat()),
        )
        return require_set(db, cursor.lastrowid)


@app.put("/sets/{set_id}")
def update_set(set_id: int, body: SetValues, db=Depends(get_db)):
    require_set(db, set_id)
    with db:
        db.execute("UPDATE sets SET weight = ?, reps = ? WHERE id = ?", (body.weight, body.reps, set_id))
        return require_set(db, set_id)


@app.delete("/sets/{set_id}", status_code=204)
def delete_set(set_id: int, db=Depends(get_db)):
    require_set(db, set_id)
    with db:
        db.execute("DELETE FROM sets WHERE id = ?", (set_id,))
    return Response(status_code=204)


app.add_middleware(PhotoPrivacyMiddleware)
app.include_router(create_router(get_db))
