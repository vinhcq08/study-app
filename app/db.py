"""SQLite storage: schema, curriculum seeding and queries."""

import json
import re
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRICULUM_FILE = ROOT / "data" / "curriculum.json"
TOPICS_FILE = ROOT / "data" / "topics.json"
DEFAULT_DB_FILE = ROOT / "study.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS lanes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL,
    row_start   INTEGER NOT NULL,
    row_end     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS subjects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    short_name  TEXT NOT NULL,
    lane_id     TEXT NOT NULL REFERENCES lanes(id),
    tier        INTEGER NOT NULL,          -- prerequisite depth (column in the tree)
    grid_row    INTEGER NOT NULL,          -- row in the tree
    kind        TEXT NOT NULL CHECK (kind IN ('course', 'gap_filler')),
    mit_match   TEXT NOT NULL CHECK (mit_match IN ('strong', 'partial', 'extra', 'gap')),
    mit_code    TEXT,
    mit_title   TEXT,
    ocw_code    TEXT,
    link_url    TEXT,
    link_text   TEXT,
    priority    TEXT,
    note        TEXT
);

-- prereq:   from_id must be done before to_id
-- supports: a gap-filler (from_id) that helps with to_id, but isn't required
-- related:  closely related subjects, no direction
CREATE TABLE IF NOT EXISTS relations (
    from_id  TEXT NOT NULL REFERENCES subjects(id),
    to_id    TEXT NOT NULL REFERENCES subjects(id),
    kind     TEXT NOT NULL CHECK (kind IN ('prereq', 'supports', 'related')),
    PRIMARY KEY (from_id, to_id, kind)
);

CREATE TABLE IF NOT EXISTS progress (
    subject_id  TEXT PRIMARY KEY REFERENCES subjects(id),
    status      TEXT NOT NULL DEFAULT 'not_started'
                CHECK (status IN ('not_started', 'in_progress', 'done')),
    semester    TEXT,
    grade       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS units (
    id          TEXT PRIMARY KEY,              -- "<subject>:u<n>"
    subject_id  TEXT NOT NULL REFERENCES subjects(id),
    name        TEXT NOT NULL,
    position    INTEGER NOT NULL
);

-- Topics removed from topics.json are marked retired instead of deleted,
-- so any progress you recorded on them is kept.
CREATE TABLE IF NOT EXISTS topics (
    id          TEXT PRIMARY KEY,              -- "<subject>:<slug of name>"
    subject_id  TEXT NOT NULL REFERENCES subjects(id),
    unit_id     TEXT NOT NULL REFERENCES units(id),
    name        TEXT NOT NULL,
    position    INTEGER NOT NULL,
    ai_key      INTEGER NOT NULL DEFAULT 0,    -- 1 = reused in graduate AI work
    retired     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS topic_progress (
    topic_id       TEXT PRIMARY KEY REFERENCES topics(id),
    mastery        INTEGER NOT NULL DEFAULT 0 CHECK (mastery BETWEEN 0 AND 4),
    notes          TEXT,
    last_reviewed  TEXT,                       -- ISO date
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per change, used for the activity chart.
CREATE TABLE IF NOT EXISTS activity (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id      TEXT NOT NULL REFERENCES topics(id),
    subject_id    TEXT NOT NULL REFERENCES subjects(id),
    kind          TEXT NOT NULL CHECK (kind IN ('mastery', 'review', 'notes')),
    mastery_from  INTEGER,
    mastery_to    INTEGER,
    at            TEXT NOT NULL                -- ISO date
);
CREATE INDEX IF NOT EXISTS activity_by_subject ON activity (subject_id, at);
"""


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def db_file() -> Path:
    return Path(os.environ.get("STUDY_APP_DB", DEFAULT_DB_FILE))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_file())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_curriculum() -> dict:
    with open(CURRICULUM_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_topics() -> dict:
    with open(TOPICS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_about", None)
    return data


def parse_topics(subject_id: str, units: list) -> tuple[list[dict], list[dict]]:
    """Turn one subject's [[unit, [topic, ...]], ...] into unit and topic rows."""
    unit_rows, topic_rows = [], []
    for u_pos, (unit_name, topic_names) in enumerate(units):
        unit_id = f"{subject_id}:u{u_pos + 1}"
        unit_rows.append({"id": unit_id, "subject_id": subject_id, "name": unit_name, "position": u_pos})
        for t_pos, raw in enumerate(topic_names):
            ai_key = raw.startswith("*")
            name = raw.lstrip("*").strip()
            topic_rows.append({
                "id": f"{subject_id}:{slugify(name)}", "subject_id": subject_id, "unit_id": unit_id,
                "name": name, "position": t_pos, "ai_key": int(ai_key),
            })
    return unit_rows, topic_rows


def init_db() -> None:
    """Create tables and (re)load the curriculum. Your progress is never touched."""
    data = load_curriculum()
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            """INSERT INTO lanes (id, name, sort_order, row_start, row_end)
               VALUES (:id, :name, :sort_order, :row_start, :row_end)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, sort_order=excluded.sort_order,
                   row_start=excluded.row_start, row_end=excluded.row_end""",
            data["lanes"],
        )
        conn.executemany(
            """INSERT INTO subjects (id, name, short_name, lane_id, tier, grid_row, kind, mit_match,
                                     mit_code, mit_title, ocw_code, link_url, link_text, priority, note)
               VALUES (:id, :name, :short_name, :lane, :tier, :row, :kind, :mit_match,
                       :mit_code, :mit_title, :ocw_code, :link_url, :link_text, :priority, :note)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, short_name=excluded.short_name,
                   lane_id=excluded.lane_id, tier=excluded.tier, grid_row=excluded.grid_row,
                   kind=excluded.kind, mit_match=excluded.mit_match, mit_code=excluded.mit_code,
                   mit_title=excluded.mit_title, ocw_code=excluded.ocw_code, link_url=excluded.link_url,
                   link_text=excluded.link_text, priority=excluded.priority, note=excluded.note""",
            data["subjects"],
        )
        conn.execute("DELETE FROM relations")
        rows = []
        for s in data["subjects"]:
            rows += [(p, s["id"], "prereq") for p in s["prereqs"]]
            rows += [(s["id"], t, "supports") for t in s["supports"]]
            rows += [(s["id"], t, "related") for t in s["related"]]
        conn.executemany("INSERT INTO relations (from_id, to_id, kind) VALUES (?, ?, ?)", rows)
        seed_topics(conn, load_topics())

        from . import study_store  # imported here to avoid a circular import
        study_store.init(conn)


def seed_topics(conn, topics_by_subject: dict) -> None:
    conn.execute("UPDATE topics SET retired = 1")
    for subject_id, units in topics_by_subject.items():
        unit_rows, topic_rows = parse_topics(subject_id, units)
        conn.executemany(
            """INSERT INTO units (id, subject_id, name, position) VALUES (:id, :subject_id, :name, :position)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, position=excluded.position""",
            unit_rows,
        )
        conn.executemany(
            """INSERT INTO topics (id, subject_id, unit_id, name, position, ai_key, retired)
               VALUES (:id, :subject_id, :unit_id, :name, :position, :ai_key, 0)
               ON CONFLICT(id) DO UPDATE SET unit_id=excluded.unit_id, name=excluded.name,
                   position=excluded.position, ai_key=excluded.ai_key, retired=0""",
            topic_rows,
        )


def fetch_lanes(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM lanes ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


def fetch_subjects(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT s.*, COALESCE(p.status, 'not_started') AS status, p.semester, p.grade
           FROM subjects s LEFT JOIN progress p ON p.subject_id = s.id
           ORDER BY s.grid_row, s.tier"""
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_relations(conn) -> list[dict]:
    rows = conn.execute("SELECT from_id, to_id, kind FROM relations").fetchall()
    return [dict(r) for r in rows]


def subject_exists(conn, subject_id: str) -> bool:
    return conn.execute("SELECT 1 FROM subjects WHERE id = ?", (subject_id,)).fetchone() is not None


def save_progress(conn, subject_id: str, status: str, semester: str | None, grade: str | None) -> None:
    conn.execute(
        """INSERT INTO progress (subject_id, status, semester, grade, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'))
           ON CONFLICT(subject_id) DO UPDATE SET status=excluded.status, semester=excluded.semester,
               grade=excluded.grade, updated_at=excluded.updated_at""",
        (subject_id, status, semester, grade),
    )


# ---- Topics ----

def fetch_topics(conn, subject_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT t.id, t.unit_id, t.name, t.position, t.ai_key,
                  COALESCE(p.mastery, 0) AS mastery, p.notes, p.last_reviewed
           FROM topics t LEFT JOIN topic_progress p ON p.topic_id = t.id
           WHERE t.subject_id = ? AND t.retired = 0
           ORDER BY t.position""",
        (subject_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_units(conn, subject_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, position FROM units WHERE subject_id = ? ORDER BY position", (subject_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_topic(conn, topic_id: str) -> dict | None:
    row = conn.execute(
        """SELECT t.id, t.subject_id, t.unit_id, t.name, t.ai_key,
                  COALESCE(p.mastery, 0) AS mastery, p.notes, p.last_reviewed
           FROM topics t LEFT JOIN topic_progress p ON p.topic_id = t.id
           WHERE t.id = ? AND t.retired = 0""",
        (topic_id,),
    ).fetchone()
    return dict(row) if row else None


def save_topic(conn, topic_id: str, mastery: int, notes: str | None, last_reviewed: str | None) -> None:
    conn.execute(
        """INSERT INTO topic_progress (topic_id, mastery, notes, last_reviewed, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'))
           ON CONFLICT(topic_id) DO UPDATE SET mastery=excluded.mastery, notes=excluded.notes,
               last_reviewed=excluded.last_reviewed, updated_at=excluded.updated_at""",
        (topic_id, mastery, notes, last_reviewed),
    )


def log_activity(conn, topic_id, subject_id, kind, at, mastery_from=None, mastery_to=None) -> None:
    conn.execute(
        """INSERT INTO activity (topic_id, subject_id, kind, mastery_from, mastery_to, at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (topic_id, subject_id, kind, mastery_from, mastery_to, at),
    )


def fetch_activity(conn, subject_id: str, since: str) -> list[dict]:
    rows = conn.execute(
        """SELECT a.kind, a.mastery_from, a.mastery_to, a.at, t.name AS topic_name
           FROM activity a JOIN topics t ON t.id = a.topic_id
           WHERE a.subject_id = ? AND a.at >= ?
           ORDER BY a.at DESC, a.id DESC""",
        (subject_id, since),
    ).fetchall()
    return [dict(r) for r in rows]


def mastery_by_subject(conn) -> dict[str, dict]:
    """Topic count and summed mastery for every subject, for the skill tree."""
    rows = conn.execute(
        """SELECT t.subject_id, COUNT(*) AS topic_count, SUM(COALESCE(p.mastery, 0)) AS mastery_sum
           FROM topics t LEFT JOIN topic_progress p ON p.topic_id = t.id
           WHERE t.retired = 0 GROUP BY t.subject_id"""
    ).fetchall()
    return {r["subject_id"]: dict(r) for r in rows}
