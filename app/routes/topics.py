"""Per-topic actions: mastery and notes, study sessions, flashcards and resources."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import clock, dashboard, db, logic, services, study_store

router = APIRouter(prefix="/api")


class TopicUpdate(BaseModel):
    mastery: int | None = Field(default=None, ge=0, le=logic.MAX_MASTERY)
    notes: str | None = Field(default=None, max_length=4000)
    reviewed: bool = False


class SessionCreate(BaseModel):
    minutes: int = Field(ge=1, le=240)


class CardCreate(BaseModel):
    front: str = Field(min_length=1, max_length=500)
    back: str = Field(min_length=1, max_length=1500)
    source: Literal["manual", "ai"] = "manual"


class CardEdit(BaseModel):
    front: str = Field(min_length=1, max_length=500)
    back: str = Field(min_length=1, max_length=1500)


class CardReview(BaseModel):
    result: Literal["again", "hard", "good", "easy"]


class ResourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    url: str = Field(pattern=r"^https?://\S+$", max_length=1000)
    kind: Literal["video", "reading", "slides", "exercises", "other"] = "other"


def _topic(conn, topic_id: str) -> dict:
    topic = db.fetch_topic(conn, topic_id)
    if topic is None:
        raise HTTPException(404, f"No topic with id '{topic_id}'")
    return topic


def _card(conn, card_id: int) -> dict:
    card = study_store.fetch_card(conn, card_id)
    if card is None:
        raise HTTPException(404, f"No flashcard with id {card_id}")
    return card


# ---- Mastery, notes, reviews ----

@router.put("/topics/{topic_id}")
def update_topic(topic_id: str, update: TopicUpdate):
    today = clock.today()
    with db.connect() as conn:
        topic = _topic(conn, topic_id)
        changes = {}
        if update.mastery is not None:
            changes["mastery"] = update.mastery
        if update.notes is not None:
            changes["notes"] = update.notes
        result = services.change_topic(conn, topic, today.isoformat(), studied=update.reviewed, **changes)
        saved = dashboard.topic_view(db.fetch_topic(conn, topic_id), today)
    return {"topic": saved, "subject_started": result["subject_started"]}


# ---- Study sessions (from the timer) ----

@router.post("/topics/{topic_id}/sessions", status_code=201)
def log_session(topic_id: str, session: SessionCreate):
    today = clock.today().isoformat()
    with db.connect() as conn:
        topic = _topic(conn, topic_id)
        study_store.add_session(conn, topic_id, topic["subject_id"], session.minutes, today)
        result = services.change_topic(conn, topic, today, studied=True)
    return {"minutes": session.minutes, **result}


# ---- Flashcards ----

@router.post("/topics/{topic_id}/cards", status_code=201)
def add_card(topic_id: str, card: CardCreate):
    with db.connect() as conn:
        _topic(conn, topic_id)
        card_id = study_store.add_card(conn, topic_id, card.front.strip(), card.back.strip(), card.source,
                                       clock.today().isoformat())
    return {"id": card_id}


@router.put("/cards/{card_id}")
def edit_card(card_id: int, card: CardEdit):
    with db.connect() as conn:
        _card(conn, card_id)
        study_store.update_card_text(conn, card_id, card.front.strip(), card.back.strip())
    return {"id": card_id}


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int):
    with db.connect() as conn:
        if not study_store.delete_card(conn, card_id):
            raise HTTPException(404, f"No flashcard with id {card_id}")


@router.post("/cards/{card_id}/review")
def review_card(card_id: int, review: CardReview):
    """Record a practice answer. The topic's mastery then follows its flashcards."""
    today = clock.today().isoformat()
    with db.connect() as conn:
        card = _card(conn, card_id)
        box = logic.next_box(card["box"], review.result)
        study_store.record_card_review(conn, card, review.result, box, today)
        topic = db.fetch_topic(conn, card["topic_id"])
        level = logic.mastery_from_cards(study_store.card_boxes(conn, card["topic_id"]))
        result = services.change_topic(conn, topic, today, mastery=level, studied=True)
    return {"card_id": card_id, "box": box, "topic_id": card["topic_id"], **result}


# ---- Resources ----

@router.post("/topics/{topic_id}/resources", status_code=201)
def add_resource(topic_id: str, resource: ResourceCreate):
    with db.connect() as conn:
        _topic(conn, topic_id)
        resource_id = study_store.add_resource(conn, topic_id, resource.title.strip(), resource.url, resource.kind)
    return {"id": resource_id}


@router.delete("/resources/{resource_id}", status_code=204)
def delete_resource(resource_id: int):
    with db.connect() as conn:
        if not study_store.delete_resource(conn, resource_id):
            raise HTTPException(404, f"No resource with id {resource_id}")
