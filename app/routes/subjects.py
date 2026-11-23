"""Subject dashboard, your exam dates, practice exams and flashcard practice lists."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import clock, dashboard, db, lectures, logic, study_store
from .. import today as plan

router = APIRouter(prefix="/api")


class PracticeExamUpdate(BaseModel):
    done: bool


class PracticeResult(BaseModel):
    score: int | None = Field(default=None, ge=0, le=100)          # percent
    minutes: int | None = Field(default=None, ge=1, le=600)
    weak_units: list[str] = Field(default_factory=list, max_length=40)


class ExamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    exam_date: date
    unit_ids: list[str] = []   # empty = the whole subject


def _require_subject(conn, subject_id: str) -> None:
    if not db.subject_exists(conn, subject_id):
        raise HTTPException(404, f"No subject with id '{subject_id}'")


@router.get("/subjects/{subject_id}/dashboard")
def get_dashboard(subject_id: str):
    with db.connect() as conn:
        _require_subject(conn, subject_id)
        return dashboard.build_dashboard(conn, subject_id, clock.today())


@router.post("/subjects/{subject_id}/exams", status_code=201)
def add_exam(subject_id: str, exam: ExamCreate):
    with db.connect() as conn:
        _require_subject(conn, subject_id)
        subject_units = [u["id"] for u in db.fetch_units(conn, subject_id)]
        unknown = [u for u in exam.unit_ids if u not in subject_units]
        if unknown:
            raise HTTPException(422, f"These units aren't part of this subject: {', '.join(unknown)}")
        unit_ids = exam.unit_ids or subject_units
        exam_id = study_store.add_exam(conn, subject_id, exam.name.strip(), exam.exam_date.isoformat(), unit_ids)
    return {"id": exam_id}


@router.delete("/exams/{exam_id}", status_code=204)
def delete_exam(exam_id: int):
    with db.connect() as conn:
        if not study_store.delete_exam(conn, exam_id):
            raise HTTPException(404, f"No exam with id {exam_id}")


@router.get("/subjects/{subject_id}/practice")
def practice(subject_id: str, topic_id: str | None = None, limit: int = 20):
    with db.connect() as conn:
        _require_subject(conn, subject_id)
        return {"cards": study_store.practice_cards(conn, subject_id, topic_id, max(1, min(limit, 50)),
                                                    clock.today().isoformat())}


@router.put("/practice-exams/{exam_id}")
def tick_practice_exam(exam_id: str, update: PracticeExamUpdate):
    """Tick a practice exam off as done, or untick it."""
    done_on = clock.today().isoformat() if update.done else None
    with db.connect() as conn:
        if not study_store.practice_exam_exists(conn, exam_id):
            raise HTTPException(404, f"No past paper with id '{exam_id}'")
        study_store.set_practice_done(conn, exam_id, done_on)
    return {"id": exam_id, "done": update.done, "done_on": done_on}


@router.put("/practice-exams/{exam_id}/result")
def save_practice_result(exam_id: str, result: PracticeResult):
    """How a past paper went: score, time taken, and the units that went badly."""
    with db.connect() as conn:
        subject_id = study_store.practice_exam_subject(conn, exam_id)
        if not subject_id:
            raise HTTPException(404, f"No past paper with id '{exam_id}'")
        units = {u["id"] for u in db.fetch_units(conn, subject_id)}
        bad = [u for u in result.weak_units if u not in units]
        if bad:
            raise HTTPException(422, f"Not a unit of this subject: {', '.join(bad)}")
        weak = list(dict.fromkeys(result.weak_units))
        study_store.save_practice_result(conn, exam_id, result.score, result.minutes, weak)
    return {"id": exam_id, "score": result.score, "minutes": result.minutes, "weak_units": weak}


@router.get("/subjects/{subject_id}/review")
def review_list(subject_id: str):
    """Topics due for review in a subject, most overdue first, for a review session."""
    now = clock.today()
    with db.connect() as conn:
        _require_subject(conn, subject_id)
        subject = next(s for s in db.fetch_subjects(conn) if s["id"] == subject_id)
        topics = [plan._due_info(t, now) for t in study_store.all_topics(conn) if t["subject_id"] == subject_id]
        due = sorted((t for t in topics if t["is_due"]), key=lambda t: t["days_until_review"])
        cards = {c["topic_id"] for c in study_store.fetch_cards_for_subject(conn, subject_id)}
        items = [{
            "id": t["id"], "name": t["name"], "unit_name": t["unit_name"], "mastery": t["mastery"],
            "days_overdue": -t["days_until_review"], "notes": db.fetch_topic(conn, t["id"])["notes"],
            "has_cards": t["id"] in cards, "lectures": lectures.for_topic(t["id"])[:2],
        } for t in due]
    return {"subject_id": subject_id, "subject_name": subject["short_name"],
            "labels": logic.MASTERY_LABELS, "topics": items}
