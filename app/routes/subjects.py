"""Subject dashboard, your exam dates, practice exams and flashcard practice lists."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import clock, dashboard, db, study_store

router = APIRouter(prefix="/api")


class PracticeExamUpdate(BaseModel):
    done: bool


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
            raise HTTPException(404, f"No practice exam with id '{exam_id}'")
        study_store.set_practice_done(conn, exam_id, done_on)
    return {"id": exam_id, "done": update.done, "done_on": done_on}
