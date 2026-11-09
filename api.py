"""Account-scoped HTTP API. Local: python run_local.py. Vercel entrypoint: api:app."""
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Response
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database import close_pool, get_db


@asynccontextmanager
async def lifespan(app):
    # Import/startup never contacts Supabase. The pool is opened lazily on demand.
    yield
    close_pool()


app = FastAPI(title='Incline API', lifespan=lifespan)


@app.middleware('http')
async def no_store(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response


def utc_today():
    return datetime.now(timezone.utc).date()


class ExerciseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)

    @field_validator('name', mode='before')
    @classmethod
    def clean_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class SetValues(BaseModel):
    model_config = ConfigDict(extra='forbid')
    weight: float = Field(gt=0, le=10000, allow_inf_nan=False)
    reps: int = Field(ge=1, le=1000, strict=True)


class SetInput(SetValues):
    exercise_id: int = Field(gt=0)
    date: date

    @field_validator('date', mode='before')
    @classmethod
    def local_date(cls, value):
        # Pydantic normally also accepts timestamps; the API accepts YYYY-MM-DD only.
        if not isinstance(value, str):
            raise ValueError('Send the local date as YYYY-MM-DD')
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError('Send the local date as YYYY-MM-DD') from None
        if parsed.isoformat() != value or abs((parsed - utc_today()).days) > 1:
            raise ValueError('The logging date must be within one day of current UTC')
        return parsed


def require_exercise(db, exercise_id):
    row = db.execute('SELECT id, name FROM public.exercises WHERE id = %s AND user_id = %s',
                     (exercise_id, db.user_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Exercise not found')
    return dict(row)


@app.get('/exercises')
def list_exercises(db=Depends(get_db, scope='function')):
    return db.execute('SELECT id, name FROM public.exercises WHERE user_id = %s ORDER BY id',
                      (db.user_id,)).fetchall()


@app.post('/exercises', status_code=201)
def create_exercise(body: ExerciseInput, db=Depends(get_db, scope='function')):
    try:
        # Postgres enforces the approved per-owner lower(name) unique index atomically.
        return db.execute('INSERT INTO public.exercises (user_id, name) VALUES (%s, %s) RETURNING id, name',
                          (db.user_id, body.name)).fetchone()
    except UniqueViolation:
        raise HTTPException(409, 'Exercise name already exists') from None


@app.get('/exercises/{exercise_id}/last-set')
def last_set(exercise_id: int, db=Depends(get_db, scope='function')):
    require_exercise(db, exercise_id)
    return db.execute(
        'SELECT id, exercise_id, weight, reps, date FROM public.sets '
        'WHERE exercise_id = %s AND user_id = %s ORDER BY id DESC LIMIT 1',
        (exercise_id, db.user_id),
    ).fetchone()


@app.get('/sets')
def list_sets(exercise_id: int | None = None, db=Depends(get_db, scope='function')):
    if exercise_id is not None:
        require_exercise(db, exercise_id)
        return db.execute('SELECT id, exercise_id, weight, reps, date FROM public.sets '
                          'WHERE exercise_id = %s AND user_id = %s ORDER BY id DESC',
                          (exercise_id, db.user_id)).fetchall()
    return db.execute('SELECT id, exercise_id, weight, reps, date FROM public.sets '
                      'WHERE user_id = %s ORDER BY id DESC', (db.user_id,)).fetchall()


@app.post('/sets', status_code=201)
def create_set(body: SetInput, db=Depends(get_db, scope='function')):
    require_exercise(db, body.exercise_id)
    try:
        return db.execute(
            'INSERT INTO public.sets (user_id, exercise_id, weight, reps, date) '
            'VALUES (%s, %s, %s, %s, %s) RETURNING id, exercise_id, weight, reps, date',
            (db.user_id, body.exercise_id, body.weight, body.reps, body.date),
        ).fetchone()
    except ForeignKeyViolation:
        raise HTTPException(404, 'Exercise not found') from None


@app.put('/sets/{set_id}')
def update_set(set_id: int, body: SetValues, db=Depends(get_db, scope='function')):
    row = db.execute('UPDATE public.sets SET weight = %s, reps = %s '
                     'WHERE id = %s AND user_id = %s RETURNING id, exercise_id, weight, reps, date',
                     (body.weight, body.reps, set_id, db.user_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Set not found')
    return row


@app.delete('/sets/{set_id}', status_code=204)
def delete_set(set_id: int, db=Depends(get_db, scope='function')):
    row = db.execute('DELETE FROM public.sets WHERE id = %s AND user_id = %s RETURNING id',
                     (set_id, db.user_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Set not found')
    return Response(status_code=204)
