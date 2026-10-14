"""Local SQLite store (data/bongo.db): gift attempts and chat messages."""
import datetime
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS gift (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    name TEXT NOT NULL,
    side TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS gift_ts ON gift(ts);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    date TEXT NOT NULL,
    speaker TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_date ON chat(date);
CREATE INDEX IF NOT EXISTS chat_speaker ON chat(speaker);
"""


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        self._db.executescript(SCHEMA)
        columns = {row[1] for row in self._db.execute('PRAGMA table_info(chat)')}
        for name, declaration in [('cat_id', 'INTEGER'), ('status', "TEXT NOT NULL DEFAULT 'recognized'"), ('score', 'REAL')]:
            if name not in columns:
                self._db.execute(f'ALTER TABLE chat ADD COLUMN {name} {declaration}')
        self._db.commit()

    def add_gift(self, ts, name, side, result):
        with self._lock, self._db:
            self._db.execute("INSERT INTO gift(ts, name, side, result) VALUES (?, ?, ?, ?)",
                             (ts, name, side, result))

    def recent_gifts(self, since):
        with self._lock:
            return self._db.execute(
                "SELECT ts, name, side, result FROM gift WHERE ts >= ? ORDER BY ts", (since,)).fetchall()

    def count_gifts(self, since, results=("clicked_ok",)):
        marks = ",".join("?" * len(results))
        with self._lock:
            return self._db.execute(
                f"SELECT COUNT(*) FROM gift WHERE ts >= ? AND result IN ({marks})", (since, *results)).fetchone()[0]

    def add_chat(self, ts, speaker, text, *, cat_id=None, status='recognized', score=None):
        date = datetime.date.fromtimestamp(ts).isoformat()
        with self._lock, self._db:
            self._db.execute("INSERT INTO chat(ts, date, speaker, text, cat_id, status, score) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (ts, date, speaker, text, cat_id, status, score))

    def query_chat_records(self):
        with self._lock:
            rows = self._db.execute('SELECT ts,speaker,text,cat_id,status,score FROM chat ORDER BY ts,id').fetchall()
            return [dict(zip(('ts','speaker','text','cat_id','status','score'), row)) for row in rows]

    def query_chat(self, date=None, speaker=None, keyword=None):
        """[(ts, speaker, text)] oldest first, filtered by any of date / speaker / keyword."""
        where, args = [], []
        if date:
            where.append("date = ?")
            args.append(date)
        if speaker:
            where.append("speaker = ?")
            args.append(speaker)
        if keyword:
            where.append("text LIKE ?")
            args.append(f"%{keyword}%")
        sql = "SELECT ts, speaker, text FROM chat" + (" WHERE " + " AND ".join(where) if where else "")
        with self._lock:
            return self._db.execute(sql + " ORDER BY ts", args).fetchall()

    def count_chat(self, date):
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM chat WHERE date = ?", (date,)).fetchone()[0]

    def chat_dates(self):
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT DISTINCT date FROM chat ORDER BY date")]

    def chat_speakers(self, date=None):
        sql, args = "SELECT DISTINCT speaker FROM chat", []
        if date:
            sql, args = sql + " WHERE date = ?", [date]
        with self._lock:
            return [r[0] for r in self._db.execute(sql + " ORDER BY speaker", args)]

    def close(self):
        self._db.close()
