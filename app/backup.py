"""Back up and restore everything you've recorded (not the curriculum, which ships with the app)."""

from . import clock

FORMAT = "study-app-backup"
VERSION = 1

# Parents before children, so restoring can insert in this order and delete in reverse.
TABLES = [
    "progress", "topic_progress", "activity", "exams", "exam_units", "study_sessions",
    "flashcards", "card_reviews", "resources", "practice_exam_progress", "plan_ticks", "daily_plans", "settings",
]


class BackupError(ValueError):
    pass


def export(conn) -> dict:
    tables = {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in TABLES}
    return {"format": FORMAT, "version": VERSION, "exported_on": clock.today().isoformat(), "tables": tables}


def restore(conn, backup: dict) -> dict[str, int]:
    """Replace all recorded data with the backup's. Runs in one transaction: all or nothing."""
    if not isinstance(backup, dict) or backup.get("format") != FORMAT:
        raise BackupError("This file isn't a Study App backup.")
    if backup.get("version", 0) > VERSION:
        raise BackupError("This backup was made by a newer version of the app.")
    tables = backup.get("tables")
    if not isinstance(tables, dict):
        raise BackupError("The backup has no data in it.")
    counts = {}
    for t in reversed(TABLES):
        conn.execute(f"DELETE FROM {t}")
    for t in TABLES:
        rows = tables.get(t, [])
        if not isinstance(rows, list):
            raise BackupError(f"The backup's {t} data is damaged.")
        columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
        for row in rows:
            if not isinstance(row, dict):
                raise BackupError(f"The backup's {t} data is damaged.")
            keep = {k: v for k, v in row.items() if k in columns}
            if not keep:
                continue
            names = ", ".join(keep)
            marks = ", ".join(f":{k}" for k in keep)
            try:
                conn.execute(f"INSERT INTO {t} ({names}) VALUES ({marks})", keep)
            except Exception as e:  # sqlite3.IntegrityError and friends
                raise BackupError(f"The backup doesn't match this version of the app ({t}: {e}).") from e
        counts[t] = len(rows)
    return counts
