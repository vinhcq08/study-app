"""The Today page: a daily plan you can tick off."""

from fastapi import APIRouter
from pydantic import BaseModel

from .. import clock, db, study_store, today

router = APIRouter(prefix="/api")


class TickUpdate(BaseModel):
    done: bool


@router.get("/today")
def get_today():
    with db.connect() as conn:
        return today.build_today(conn, clock.today())


@router.put("/today/ticks/{item_key:path}")
def tick_plan_item(item_key: str, update: TickUpdate):
    key = item_key[:200]
    with db.connect() as conn:
        study_store.set_plan_tick(conn, clock.today().isoformat(), key, update.done)
    return {"key": key, "done": update.done}
