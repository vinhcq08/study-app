"""The Today page: a daily plan you can work through and tick off."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import clock, db, today

router = APIRouter(prefix="/api")


class TickUpdate(BaseModel):
    done: bool


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
