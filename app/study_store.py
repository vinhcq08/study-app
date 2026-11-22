"""Storage for study features: exams, study sessions, flashcards, resources and topic links."""

import json

from . import clock, db

SCHEMA = """
CREATE TABLE IF NOT EXISTS exams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  TEXT NOT NULL REFERENCES subjects(id),
    name        TEXT NOT NULL,
    exam_date   TEXT NOT NULL                 -- ISO date
);

-- Which units an exam covers.
CREATE TABLE IF NOT EXISTS exam_units (
    exam_id  INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    unit_id  TEXT NOT NULL REFERENCES units(id),
    PRIMARY KEY (exam_id, unit_id)
);

CREATE TABLE IF NOT EXISTS study_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id    TEXT NOT NULL REFERENCES topics(id),
    subject_id  TEXT NOT NULL REFERENCES subjects(id),
    minutes     INTEGER NOT NULL CHECK (minutes BETWEEN 1 AND 240),
    studied_on  TEXT NOT NULL                 -- ISO date
);

-- Leitner boxes: 0 = new, 1 = keep missing it ... 4 = solid.
CREATE TABLE IF NOT EXISTS flashcards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id        TEXT NOT NULL REFERENCES topics(id),
    front           TEXT NOT NULL,
    back            TEXT NOT NULL,
    box             INTEGER NOT NULL DEFAULT 0 CHECK (box BETWEEN 0 AND 4),
    last_result     TEXT,
    last_practised  TEXT,
    created_on      TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'ai'))
);

CREATE TABLE IF NOT EXISTS card_reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id      INTEGER NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
    topic_id     TEXT NOT NULL REFERENCES topics(id),
    result       TEXT NOT NULL CHECK (result IN ('again', 'hard', 'good', 'easy')),
    reviewed_on  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resources (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id  TEXT NOT NULL REFERENCES topics(id),
    title     TEXT NOT NULL,
    url       TEXT NOT NULL,
    kind      TEXT NOT NULL CHECK (kind IN ('video', 'reading', 'slides', 'exercises', 'other'))
);

-- Past exams from other universities, to work through and tick off.
CREATE TABLE IF NOT EXISTS practice_exams (
    id             TEXT PRIMARY KEY,          -- "<subject>:<slug of course and title>"
    subject_id     TEXT NOT NULL REFERENCES subjects(id),
    position       INTEGER NOT NULL,
    title          TEXT NOT NULL,
    school         TEXT NOT NULL,
    course         TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('quiz', 'midterm', 'final', 'practice')),
    url            TEXT NOT NULL,
    solutions_url  TEXT,
    note           TEXT
);

CREATE TABLE IF NOT EXISTS practice_exam_units (
    exam_id  TEXT NOT NULL REFERENCES practice_exams(id) ON DELETE CASCADE,
    unit_id  TEXT NOT NULL REFERENCES units(id),
    PRIMARY KEY (exam_id, unit_id)
);

CREATE TABLE IF NOT EXISTS practice_exam_progress (
    exam_id  TEXT PRIMARY KEY REFERENCES practice_exams(id) ON DELETE CASCADE,
    done_on  TEXT NOT NULL
);

-- Today's plan, built once per day so it doesn't reshuffle while you work.
CREATE TABLE IF NOT EXISTS daily_plans (
    day    TEXT PRIMARY KEY,
    items  TEXT NOT NULL            -- JSON list of plan items
);

-- Items you ticked off on the Today page, per day.
CREATE TABLE IF NOT EXISTS plan_ticks (
    day       TEXT NOT NULL,
    item_key  TEXT NOT NULL,
    PRIMARY KEY (day, item_key)
);

-- from_topic is a foundation that to_topic builds on.
CREATE TABLE IF NOT EXISTS topic_links (
    from_topic  TEXT NOT NULL REFERENCES topics(id),
    to_topic    TEXT NOT NULL REFERENCES topics(id),
    why         TEXT NOT NULL,
    PRIMARY KEY (from_topic, to_topic)
);
"""

TOPIC_LINKS_FILE = db.ROOT / "data" / "topic_links.json"
PRACTICE_EXAMS_FILE = db.ROOT / "data" / "practice_exams.json"
PRACTICE_KINDS = ("quiz", "midterm", "final", "practice")


def load_topic_links() -> list[dict]:
    """Read topic_links.json and turn subject + topic names into topic ids."""
    with open(TOPIC_LINKS_FILE, encoding="utf-8") as f:
        raw = json.load(f)["links"]
    return [
        {
            "from_topic": f"{a_subject}:{db.slugify(a_topic)}",
            "to_topic": f"{b_subject}:{db.slugify(b_topic)}",
            "why": why,
        }
        for a_subject, a_topic, b_subject, b_topic, why in raw
    ]


# Columns added after the first release. Older databases get them on startup.
ADDED_COLUMNS = {
    "flashcards": {"due_on": "TEXT"},
    "practice_exam_progress": {"score": "INTEGER", "minutes": "INTEGER", "weak_units": "TEXT"},
}


def migrate(conn) -> None:
    for table, columns in ADDED_COLUMNS.items():
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


def init(conn) -> None:
    conn.executescript(SCHEMA)
    migrate(conn)
    links = load_topic_links()
    known = {r["id"] for r in conn.execute("SELECT id FROM topics WHERE retired = 0")}
    missing = [l for l in links if l["from_topic"] not in known or l["to_topic"] not in known]
    if missing:
        names = ", ".join(f"{l['from_topic']} -> {l['to_topic']}" for l in missing)
        raise ValueError(f"topic_links.json refers to topics that don't exist: {names}")
    conn.execute("DELETE FROM topic_links")
    conn.executemany("INSERT INTO topic_links (from_topic, to_topic, why) VALUES (:from_topic, :to_topic, :why)", links)
    seed_practice_exams(conn)


def load_practice_exams(conn) -> list[dict]:
    """Read practice_exams.json and resolve unit positions to unit ids. Raises on bad data."""
    with open(PRACTICE_EXAMS_FILE, encoding="utf-8") as f:
        by_subject = json.load(f)["exams"]
    exams = []
    for subject_id, items in by_subject.items():
        if not db.subject_exists(conn, subject_id):
            raise ValueError(f"practice_exams.json: unknown subject '{subject_id}'")
        unit_ids = [u["id"] for u in db.fetch_units(conn, subject_id)]
        for position, e in enumerate(items):
            where = f"practice_exams.json: {subject_id} / {e.get('title')}"
            if e["kind"] not in PRACTICE_KINDS:
                raise ValueError(f"{where}: kind must be one of {PRACTICE_KINDS}")
            for key in ("url", "solutions_url"):
                if e.get(key) and not e[key].startswith("https://"):
                    raise ValueError(f"{where}: {key} must start with https://")
            if e["units"] == "all":
                covers = unit_ids
            else:
                bad = [n for n in e["units"] if not 1 <= n <= len(unit_ids)]
                if bad:
                    raise ValueError(f"{where}: unit numbers {bad} don't exist (subject has {len(unit_ids)} units)")
                covers = [unit_ids[n - 1] for n in e["units"]]
            exams.append({
                "id": f"{subject_id}:{db.slugify(e['course'] + ' ' + e['title'])}",
                "subject_id": subject_id, "position": position, "title": e["title"], "school": e["school"],
                "course": e["course"], "kind": e["kind"], "url": e["url"],
                "solutions_url": e.get("solutions_url"), "note": e.get("note"), "unit_ids": covers,
            })
    ids = [e["id"] for e in exams]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"practice_exams.json: duplicate exams {sorted(dupes)}")
    return exams


def seed_practice_exams(conn) -> None:
    """Load the catalog. Ticks on exams that are still listed are kept."""
    exams = load_practice_exams(conn)
    keep = [e["id"] for e in exams]
    marks = ",".join("?" * len(keep))
    conn.execute(f"DELETE FROM practice_exams WHERE id NOT IN ({marks})", keep)
    conn.executemany(
        """INSERT INTO practice_exams (id, subject_id, position, title, school, course, kind, url, solutions_url, note)
           VALUES (:id, :subject_id, :position, :title, :school, :course, :kind, :url, :solutions_url, :note)
           ON CONFLICT(id) DO UPDATE SET position=excluded.position, title=excluded.title, school=excluded.school,
               course=excluded.course, kind=excluded.kind, url=excluded.url,
               solutions_url=excluded.solutions_url, note=excluded.note""",
        exams,
    )
    conn.execute("DELETE FROM practice_exam_units")
    conn.executemany("INSERT INTO practice_exam_units (exam_id, unit_id) VALUES (?, ?)",
                     [(e["id"], u) for e in exams for u in e["unit_ids"]])


def rows(conn, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---- Exams ----

def fetch_exams(conn, subject_id: str | None = None) -> list[dict]:
    where, params = ("WHERE e.subject_id = ?", (subject_id,)) if subject_id else ("", ())
    exams = rows(conn, f"SELECT e.id, e.subject_id, e.name, e.exam_date FROM exams e {where} ORDER BY e.exam_date", params)
    for e in exams:
        e["unit_ids"] = [r["unit_id"] for r in rows(conn, "SELECT unit_id FROM exam_units WHERE exam_id = ?", (e["id"],))]
    return exams


def add_exam(conn, subject_id: str, name: str, exam_date: str, unit_ids: list[str]) -> int:
    cur = conn.execute("INSERT INTO exams (subject_id, name, exam_date) VALUES (?, ?, ?)", (subject_id, name, exam_date))
    conn.executemany("INSERT INTO exam_units (exam_id, unit_id) VALUES (?, ?)", [(cur.lastrowid, u) for u in unit_ids])
    return cur.lastrowid


def delete_exam(conn, exam_id: int) -> bool:
    return conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,)).rowcount > 0


# ---- Study sessions ----

def add_session(conn, topic_id: str, subject_id: str, minutes: int, studied_on: str) -> None:
    conn.execute(
        "INSERT INTO study_sessions (topic_id, subject_id, minutes, studied_on) VALUES (?, ?, ?, ?)",
        (topic_id, subject_id, minutes, studied_on),
    )


def fetch_sessions(conn, subject_id: str | None, since: str) -> list[dict]:
    sql = """SELECT s.topic_id, s.subject_id, s.minutes, s.studied_on, t.name AS topic_name
             FROM study_sessions s JOIN topics t ON t.id = s.topic_id WHERE s.studied_on >= ?"""
    params = [since]
    if subject_id:
        sql += " AND s.subject_id = ?"
        params.append(subject_id)
    return rows(conn, sql + " ORDER BY s.studied_on DESC, s.id DESC", params)


def minutes_by_topic(conn, subject_id: str) -> dict[str, int]:
    return {r["topic_id"]: r["m"] for r in rows(
        conn, "SELECT topic_id, SUM(minutes) AS m FROM study_sessions WHERE subject_id = ? GROUP BY topic_id", (subject_id,))}


# ---- Flashcards ----

CARD_COLUMNS = "c.id, c.topic_id, c.front, c.back, c.box, c.last_result, c.last_practised, c.source, c.due_on"


def fetch_cards_for_subject(conn, subject_id: str) -> list[dict]:
    return rows(conn, f"""SELECT {CARD_COLUMNS} FROM flashcards c JOIN topics t ON t.id = c.topic_id
                          WHERE t.subject_id = ? AND t.retired = 0 ORDER BY c.id""", (subject_id,))


def fetch_card(conn, card_id: int) -> dict | None:
    found = rows(conn, f"""SELECT {CARD_COLUMNS}, t.subject_id FROM flashcards c JOIN topics t ON t.id = c.topic_id
                           WHERE c.id = ?""", (card_id,))
    return found[0] if found else None


def practice_cards(conn, subject_id: str, topic_id: str | None, limit: int, today: str = "9999-12-31") -> list[dict]:
    """Due cards first, then the weakest and least recently practised."""
    sql = f"""SELECT {CARD_COLUMNS}, t.name AS topic_name FROM flashcards c JOIN topics t ON t.id = c.topic_id
              WHERE t.subject_id = ? AND t.retired = 0"""
    params: list = [subject_id]
    if topic_id:
        sql += " AND c.topic_id = ?"
        params.append(topic_id)
    sql += """ ORDER BY (c.due_on IS NOT NULL AND c.due_on > ?), c.box,
               c.last_practised IS NOT NULL, c.last_practised, c.id LIMIT ?"""
    params += [today, limit]
    return rows(conn, sql, params)


def add_card(conn, topic_id: str, front: str, back: str, source: str, created_on: str) -> int:
    cur = conn.execute(
        "INSERT INTO flashcards (topic_id, front, back, source, created_on) VALUES (?, ?, ?, ?, ?)",
        (topic_id, front, back, source, created_on),
    )
    return cur.lastrowid


def update_card_text(conn, card_id: int, front: str, back: str) -> None:
    conn.execute("UPDATE flashcards SET front = ?, back = ? WHERE id = ?", (front, back, card_id))


def delete_card(conn, card_id: int) -> bool:
    return conn.execute("DELETE FROM flashcards WHERE id = ?", (card_id,)).rowcount > 0


def record_card_review(conn, card: dict, result: str, new_box: int, on: str, due_on: str) -> None:
    conn.execute(
        "UPDATE flashcards SET box = ?, last_result = ?, last_practised = ?, due_on = ? WHERE id = ?",
        (new_box, result, on, due_on, card["id"]),
    )
    conn.execute(
        "INSERT INTO card_reviews (card_id, topic_id, result, reviewed_on) VALUES (?, ?, ?, ?)",
        (card["id"], card["topic_id"], result, on),
    )


def card_boxes(conn, topic_id: str) -> list[int]:
    return [r["box"] for r in rows(conn, "SELECT box FROM flashcards WHERE topic_id = ?", (topic_id,))]


def card_review_days(conn, subject_id: str, since: str) -> list[str]:
    return [r["reviewed_on"] for r in rows(
        conn, """SELECT r.reviewed_on FROM card_reviews r JOIN topics t ON t.id = r.topic_id
                 WHERE t.subject_id = ? AND r.reviewed_on >= ?""", (subject_id, since))]


# ---- Resources ----

def fetch_resources_for_subject(conn, subject_id: str) -> list[dict]:
    return rows(conn, """SELECT r.id, r.topic_id, r.title, r.url, r.kind FROM resources r
                         JOIN topics t ON t.id = r.topic_id WHERE t.subject_id = ? ORDER BY r.id""", (subject_id,))


def add_resource(conn, topic_id: str, title: str, url: str, kind: str) -> int:
    cur = conn.execute("INSERT INTO resources (topic_id, title, url, kind) VALUES (?, ?, ?, ?)", (topic_id, title, url, kind))
    return cur.lastrowid


def delete_resource(conn, resource_id: int) -> bool:
    return conn.execute("DELETE FROM resources WHERE id = ?", (resource_id,)).rowcount > 0


# ---- Topic links ----

def fetch_links_for_subject(conn, subject_id: str) -> list[dict]:
    """Every link that starts or ends in this subject, with names for display."""
    return rows(conn, """
        SELECT l.from_topic, l.to_topic, l.why,
               a.name AS from_name, a.subject_id AS from_subject, sa.short_name AS from_subject_name,
               b.name AS to_name, b.subject_id AS to_subject, sb.short_name AS to_subject_name
        FROM topic_links l
        JOIN topics a ON a.id = l.from_topic JOIN subjects sa ON sa.id = a.subject_id
        JOIN topics b ON b.id = l.to_topic JOIN subjects sb ON sb.id = b.subject_id
        WHERE a.subject_id = ? OR b.subject_id = ?""", (subject_id, subject_id))


# ---- Signals for weak spots ----

def mark_downs(conn, since: str, subject_id: str | None = None) -> dict[str, int]:
    """How often each topic's mastery was lowered since a date."""
    sql = "SELECT topic_id, COUNT(*) AS n FROM activity WHERE kind = 'mastery' AND mastery_to < mastery_from AND at >= ?"
    params = [since]
    if subject_id:
        sql += " AND subject_id = ?"
        params.append(subject_id)
    return {r["topic_id"]: r["n"] for r in rows(conn, sql + " GROUP BY topic_id", params)}


def missed_cards(conn, since: str, subject_id: str | None = None) -> dict[str, int]:
    """How many 'again' answers each topic's flashcards got since a date."""
    sql = """SELECT r.topic_id, COUNT(*) AS n FROM card_reviews r JOIN topics t ON t.id = r.topic_id
             WHERE r.result = 'again' AND r.reviewed_on >= ?"""
    params = [since]
    if subject_id:
        sql += " AND t.subject_id = ?"
        params.append(subject_id)
    return {r["topic_id"]: r["n"] for r in rows(conn, sql + " GROUP BY r.topic_id", params)}


def started_topics(conn) -> list[dict]:
    """Every topic you've started, across all subjects."""
    return rows(conn, """
        SELECT t.id, t.name, t.subject_id, t.unit_id, s.short_name AS subject_name, p.mastery, p.last_reviewed,
               (SELECT COUNT(*) FROM flashcards c WHERE c.topic_id = t.id) AS card_count
        FROM topics t JOIN topic_progress p ON p.topic_id = t.id JOIN subjects s ON s.id = t.subject_id
        WHERE t.retired = 0 AND p.mastery > 0""")


# ---- Practice exams ----

def fetch_practice_exams(conn, subject_id: str) -> list[dict]:
    exams = rows(conn, """SELECT e.id, e.title, e.school, e.course, e.kind, e.url, e.solutions_url, e.note,
                                 p.done_on, p.score, p.minutes, p.weak_units
                          FROM practice_exams e LEFT JOIN practice_exam_progress p ON p.exam_id = e.id
                          WHERE e.subject_id = ? ORDER BY e.position""", (subject_id,))
    for e in exams:
        e["unit_ids"] = [r["unit_id"] for r in rows(conn, "SELECT unit_id FROM practice_exam_units WHERE exam_id = ?", (e["id"],))]
        e["weak_units"] = json.loads(e["weak_units"]) if e["weak_units"] else []
    return exams


def practice_exam_subject(conn, exam_id: str) -> str | None:
    row = conn.execute("SELECT subject_id FROM practice_exams WHERE id = ?", (exam_id,)).fetchone()
    return row["subject_id"] if row else None


def save_practice_result(conn, exam_id: str, score: int | None, minutes: int | None, weak_units: list[str]) -> None:
    """Record how a past paper went. Saving a result also ticks the paper off."""
    conn.execute("""INSERT INTO practice_exam_progress (exam_id, done_on, score, minutes, weak_units)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(exam_id) DO UPDATE SET score = excluded.score, minutes = excluded.minutes,
                                                       weak_units = excluded.weak_units""",
                 (exam_id, clock.today().isoformat(), score, minutes, json.dumps(weak_units) if weak_units else None))


def weak_paper_units(conn, since: str, subject_id: str | None = None) -> set[str]:
    """Units that went badly on past papers done since a date."""
    sql = """SELECT p.weak_units FROM practice_exam_progress p JOIN practice_exams e ON e.id = p.exam_id
             WHERE p.weak_units IS NOT NULL AND p.done_on >= ?"""
    args = [since]
    if subject_id:
        sql += " AND e.subject_id = ?"
        args.append(subject_id)
    return {u for r in rows(conn, sql, args) for u in json.loads(r["weak_units"])}


def practice_exam_exists(conn, exam_id: str) -> bool:
    return conn.execute("SELECT 1 FROM practice_exams WHERE id = ?", (exam_id,)).fetchone() is not None


def set_practice_done(conn, exam_id: str, done_on: str | None) -> None:
    if done_on:  # ticking again keeps the first date and any result
        conn.execute("""INSERT INTO practice_exam_progress (exam_id, done_on) VALUES (?, ?)
                        ON CONFLICT(exam_id) DO NOTHING""", (exam_id, done_on))
    else:
        conn.execute("DELETE FROM practice_exam_progress WHERE exam_id = ?", (exam_id,))


def practice_totals(conn) -> dict:
    row = conn.execute("""SELECT COUNT(*) AS total, COUNT(p.exam_id) AS done
                          FROM practice_exams e LEFT JOIN practice_exam_progress p ON p.exam_id = e.id""").fetchone()
    return {"total": row["total"], "done": row["done"]}


# ---- Today page ----

def all_topics(conn) -> list[dict]:
    """Every current topic with its unit, subject and progress."""
    return rows(conn, """
        SELECT t.id, t.name, t.subject_id, t.unit_id, t.position, u.position AS unit_pos, u.name AS unit_name,
               s.short_name AS subject_name, COALESCE(p.mastery, 0) AS mastery, p.last_reviewed
        FROM topics t JOIN units u ON u.id = t.unit_id JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN topic_progress p ON p.topic_id = t.id
        WHERE t.retired = 0 ORDER BY u.position, t.position""")


def plan_ticks(conn, day: str) -> set[str]:
    return {r["item_key"] for r in rows(conn, "SELECT item_key FROM plan_ticks WHERE day = ?", (day,))}


def set_plan_tick(conn, day: str, item_key: str, done: bool) -> None:
    if done:
        conn.execute("INSERT OR IGNORE INTO plan_ticks (day, item_key) VALUES (?, ?)", (day, item_key))
    else:
        conn.execute("DELETE FROM plan_ticks WHERE day = ? AND item_key = ?", (day, item_key))


def study_days(conn) -> set[str]:
    """Every date with any study activity."""
    return {r["d"] for r in rows(conn, """
        SELECT at AS d FROM activity UNION SELECT studied_on FROM study_sessions
        UNION SELECT reviewed_on FROM card_reviews UNION SELECT day FROM plan_ticks""")}


def practice_counts_by_subject(conn) -> dict[str, dict]:
    return {r["subject_id"]: {"total": r["total"], "done": r["done"]} for r in rows(conn, """
        SELECT e.subject_id, COUNT(*) AS total, COUNT(p.exam_id) AS done
        FROM practice_exams e LEFT JOIN practice_exam_progress p ON p.exam_id = e.id GROUP BY e.subject_id""")}


def get_daily_plan(conn, day: str) -> list[dict] | None:
    row = conn.execute("SELECT items FROM daily_plans WHERE day = ?", (day,)).fetchone()
    return json.loads(row["items"]) if row else None


def save_daily_plan(conn, day: str, items: list[dict]) -> None:
    conn.execute("""INSERT INTO daily_plans (day, items) VALUES (?, ?)
                    ON CONFLICT(day) DO UPDATE SET items = excluded.items""", (day, json.dumps(items)))


def card_reviews_on(conn, day: str) -> dict[str, int]:
    """Flashcard answers given on a day, per subject."""
    return {r["subject_id"]: r["n"] for r in rows(conn, """
        SELECT t.subject_id, COUNT(*) AS n FROM card_reviews r JOIN topics t ON t.id = r.topic_id
        WHERE r.reviewed_on = ? GROUP BY t.subject_id""", (day,))}


def done_practice_exam_ids(conn) -> set[str]:
    return {r["exam_id"] for r in rows(conn, "SELECT exam_id FROM practice_exam_progress")}


def due_card_counts(conn, today: str) -> dict[str, int]:
    """Flashcards due today (new cards count as due), per subject."""
    return {r["subject_id"]: r["n"] for r in rows(conn, """
        SELECT t.subject_id, COUNT(*) AS n FROM flashcards c JOIN topics t ON t.id = c.topic_id
        WHERE t.retired = 0 AND (c.due_on IS NULL OR c.due_on <= ?) GROUP BY t.subject_id""", (today,))}
