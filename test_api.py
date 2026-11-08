"""Exercise the ASGI API with an isolated database and no extra test packages."""
from contextlib import closing
import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

import api


class ApiTest(unittest.TestCase):
    def test_progress_photos_are_not_exposed(self):
        paths = self.request("GET", "/openapi.json")[1]["paths"]
        self.assertFalse(any(path.startswith("/progress-photos") for path in paths))
        for method, path in [("GET", "/progress-photos"), ("POST", "/progress-photos"),
                             ("GET", "/progress-photos/1/image"), ("DELETE", "/progress-photos/1")]:
            self.assertEqual(self.request(method, path)[0], 404)

    def test_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            original = api.DB_PATH
            api.DB_PATH = Path(folder) / "test.db"
            try:
                with closing(sqlite3.connect(api.DB_PATH)) as db:
                    db.executescript("""
                        CREATE TABLE exercises (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);
                        CREATE TABLE sets (id INTEGER PRIMARY KEY AUTOINCREMENT, exercise_id INTEGER NOT NULL,
                            weight REAL NOT NULL, reps INTEGER NOT NULL, date TEXT NOT NULL);
                    """)
                self.check_endpoints()
            finally:
                api.DB_PATH = original

    def request(self, method, path, body=None):
        target = urlsplit(path)
        async def run():
            messages = []
            async def receive():
                return {"type": "http.request", "body": json.dumps(body).encode() if body is not None else b"", "more_body": False}
            async def send(message):
                messages.append(message)
            await api.app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                           "method": method, "scheme": "http", "path": target.path, "raw_path": target.path.encode(),
                           "query_string": target.query.encode(), "headers": [(b"content-type", b"application/json")],
                           "client": ("127.0.0.1", 1), "server": ("test", 80)}, receive, send)
            status = messages[0]["status"]
            payload = b"".join(m.get("body", b"") for m in messages[1:])
            return status, json.loads(payload) if payload else None
        return asyncio.run(run())

    def check_endpoints(self):
        self.assertEqual(self.request("GET", "/openapi.json")[0], 200)
        status, exercise = self.request("POST", "/exercises", {"name": " Bench Press "})
        self.assertEqual(status, 201)
        eid = exercise["id"]
        self.assertEqual(self.request("POST", "/exercises", {"name": "BENCH PRESS"})[0], 409)
        self.assertEqual(self.request("POST", "/exercises", {"name": "  "})[0], 422)
        self.assertEqual(self.request("GET", f"/exercises/{eid}/last-set"), (200, None))
        for weight, reps in [(0, 8), (-1, 8), (100, 0), (100, -1), (100, 1.5)]:
            self.assertEqual(self.request("POST", "/sets", {"exercise_id": eid, "weight": weight, "reps": reps})[0], 422)
        self.assertEqual(self.request("POST", "/sets", {"exercise_id": 999, "weight": 100, "reps": 8})[0], 404)
        for weight in [100, 105]:
            status, entry = self.request("POST", "/sets", {"exercise_id": eid, "weight": weight, "reps": 8})
            self.assertEqual(status, 201)
        sid = entry["id"]
        status, other = self.request("POST", "/exercises", {"name": "Squat"})
        self.assertEqual(status, 201)
        status, squat = self.request("POST", "/sets", {"exercise_id": other["id"], "weight": 135, "reps": 5})
        self.assertEqual(status, 201)
        status, history = self.request("GET", "/sets")
        self.assertEqual(status, 200)
        self.assertEqual([row["id"] for row in history], [squat["id"], sid, sid - 1])
        self.assertEqual(set(history[0]), {"id", "exercise_id", "weight", "reps", "date"})
        status, filtered = self.request("GET", f"/sets?exercise_id={eid}")
        self.assertEqual(status, 200)
        self.assertEqual([row["id"] for row in filtered], [sid, sid - 1])
        self.assertTrue(all(row["exercise_id"] == eid for row in filtered))
        self.assertEqual(self.request("GET", "/sets?exercise_id=999")[0], 404)
        self.assertEqual(self.request("GET", "/sets?exercise_id=invalid")[0], 422)
        _, empty = self.request("POST", "/exercises", {"name": "Deadlift"})
        self.assertEqual(self.request("GET", f"/sets?exercise_id={empty['id']}"), (200, []))
        self.assertEqual(self.request("GET", f"/exercises/{eid}/last-set")[1]["id"], sid)
        self.assertEqual(len(self.request("GET", "/sets")[1]), 3)
        self.assertEqual(self.request("PUT", f"/sets/{sid}", {"weight": 0, "reps": 8})[0], 422)
        status, edited = self.request("PUT", f"/sets/{sid}", {"weight": 110, "reps": 9})
        self.assertEqual(status, 200)
        self.assertEqual(edited, {**entry, "weight": 110, "reps": 9})
        self.assertEqual(self.request("GET", f"/exercises/{eid}/last-set")[1], edited)
        self.assertEqual(self.request("GET", f"/sets?exercise_id={eid}")[1][0], edited)
        for values in [{"weight": -1, "reps": 8}, {"weight": 100, "reps": 0},
                       {"weight": 100, "reps": 1.5}, {"weight": 100, "reps": 8, "date": "2000-01-01"}]:
            self.assertEqual(self.request("PUT", f"/sets/{sid}", values)[0], 422)
        self.assertEqual(self.request("GET", f"/exercises/{eid}/last-set")[1], edited)
        self.assertEqual(self.request("PUT", "/sets/999", {"weight": 100, "reps": 8})[0], 404)
        self.assertEqual(self.request("DELETE", f"/sets/{sid}")[0], 204)
        self.assertEqual(self.request("DELETE", f"/sets/{sid}")[0], 404)
        remaining = self.request("GET", "/sets")[1]
        self.assertEqual([row["id"] for row in remaining], [squat["id"], sid - 1])
        self.assertEqual(self.request("GET", f"/exercises/{eid}/last-set")[1]["id"], sid - 1)


if __name__ == "__main__":
    unittest.main()
