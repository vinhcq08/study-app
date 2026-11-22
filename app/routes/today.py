"""The Today page: a daily plan you can work through and tick off."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import clock, db, study_store, today

router = APIRouter(prefix="/api")


class TickUpdate(BaseModel):
    done: bool


class Settings(BaseModel):
    daily_minutes: int | None = Field(default=None, ge=10, le=720)   # None: no limit


@router.get("/today")
def get_today():
    with db.connect() as conn:
        return today.build_today(conn, clock.today())


@router.put("/today/ticks/{item_key:path}")
def tick_plan_item(item_key: str, update: TickUpdate):
    with db.connect() as conn:
        try:
            today.tick(conn, clock.today(), item_key, update.done)
        except KeyError:
            raise HTTPException(404, f"Today's plan has no item '{item_key}'")
    return {"key": item_key, "done": update.done}


@router.post("/today/more")
def add_to_plan():
    with db.connect() as conn:
        added = today.add_more(conn, clock.today())
    return {"added": added}


@router.post("/today/rebuild")
def rebuild_plan():
    with db.connect() as conn:
        today.rebuild(conn, clock.today())
    return {"rebuilt": True}


@router.get("/settings")
def get_settings():
    with db.connect() as conn:
        return {"daily_minutes": today.daily_budget(conn)}


@router.put("/settings")
def save_settings(settings: Settings):
    """Save your settings. A new daily time budget rebuilds today's plan, keeping what's done."""
    with db.connect() as conn:
        changed = settings.daily_minutes != today.daily_budget(conn)
        study_store.set_setting(conn, today.BUDGET_KEY, settings.daily_minutes)
        if changed:
            today.rebuild(conn, clock.today())
    return {"daily_minutes": settings.daily_minutes}
