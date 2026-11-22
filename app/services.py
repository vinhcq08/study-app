"""Changes that touch several tables at once."""

from . import db, logic

KEEP = object()  # "leave this field as it is"


def change_topic(conn, topic: dict, on: str, *, mastery=KEEP, notes=KEEP, studied: bool = False) -> dict:
    """Update a topic's mastery, notes or review date, log the activity, and start the subject if needed.

    `studied=True` means you just reviewed, practised or studied the topic: its review clock restarts,
    and a topic you hadn't started moves to Learning.
    """
    topic_id, subject_id = topic["id"], topic["subject_id"]
    level, text, last = topic["mastery"], topic["notes"], topic["last_reviewed"]

    if mastery is not KEEP and mastery != level:
        db.log_activity(conn, topic_id, subject_id, "mastery", on, level, mastery)
        level = mastery
        last = on if level > 0 else None

    if studied:
        if level == 0:
            db.log_activity(conn, topic_id, subject_id, "mastery", on, 0, 1)
            level = 1
        elif mastery is KEEP or mastery == topic["mastery"]:
            db.log_activity(conn, topic_id, subject_id, "review", on, level, level)
        last = on

    if notes is not KEEP:
        new_text = (notes or "").strip() or None
        if new_text != text:
            db.log_activity(conn, topic_id, subject_id, "notes", on)
            text = new_text

    db.save_topic(conn, topic_id, level, text, last)

    subject_started = False
    if level > 0:
        subject = next(s for s in db.fetch_subjects(conn) if s["id"] == subject_id)
        if subject["status"] == "not_started":
            db.save_progress(conn, subject_id, "in_progress", subject["semester"], subject["grade"])
            subject_started = True
    return {"mastery_before": topic["mastery"], "mastery": level, "subject_started": subject_started}


def mastery_label(level: int) -> str:
    return logic.MASTERY_LABELS[level]
