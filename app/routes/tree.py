"""Skill tree: subjects, prerequisites, progress, and the cross-subject overview."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import clock, dashboard, db, logic, study_store

router = APIRouter(prefix="/api")


class ProgressUpdate(BaseModel):
    status: Literal["not_started", "in_progress", "done"]
    semester: str | None = Field(default=None, max_length=30)
    grade: str | None = Field(default=None, max_length=10)


def _load(conn):
    subjects = {s["id"]: s for s in db.fetch_subjects(conn)}
    return subjects, db.fetch_relations(conn)


@router.get("/tree")
def get_tree():
    now = clock.today()
    with db.connect() as conn:
        lanes = db.fetch_lanes(conn)
        subjects, relations = _load(conn)
        mastery = db.mastery_by_subject(conn)
        practice = study_store.practice_counts_by_subject(conn)
        started = study_store.started_topics(conn)
    due = {}
    for t in started:
        last = date.fromisoformat(t["last_reviewed"]) if t["last_reviewed"] else None
        nxt = logic.next_review(t["mastery"], last)
        if nxt and nxt <= now:
            due[t["subject_id"]] = due.get(t["subject_id"], 0) + 1
    states = logic.compute_states(subjects, relations)
    for sid, s in subjects.items():
        s["state"] = states[sid]
        m = mastery.get(sid)
        s["topic_count"] = m["topic_count"] if m else 0
        s["mastery_pct"] = round(100 * m["mastery_sum"] / (logic.MAX_MASTERY * m["topic_count"])) if m else 0
        s["level"], s["next_level_at"] = logic.subject_level(s["mastery_pct"])
        s["due_count"] = due.get(sid, 0)
        p = practice.get(sid, {"total": 0, "done": 0})
        s["practice_total"], s["practice_done"] = p["total"], p["done"]
    return {"lanes": lanes, "subjects": list(subjects.values()), "relations": relations}


@router.put("/progress/{subject_id}")
def update_progress(subject_id: str, update: ProgressUpdate):
    with db.connect() as conn:
        if not db.subject_exists(conn, subject_id):
            raise HTTPException(404, f"No subject with id '{subject_id}'")
        subjects, relations = _load(conn)
        before = logic.compute_states(subjects, relations)
        semester = (update.semester or "").strip() or None
        grade = (update.grade or "").strip() or None
        db.save_progress(conn, subject_id, update.status, semester, grade)
        subjects, relations = _load(conn)
        after = logic.compute_states(subjects, relations)
    return {"subject_id": subject_id, "status": update.status, "semester": semester, "grade": grade,
            "state": after[subject_id], "unlocked": logic.newly_unlocked(before, after)}


@router.get("/overview")
def get_overview():
    with db.connect() as conn:
        return dashboard.build_overview(conn, clock.today())
