"""FastAPI app: JSON API under /api and the web pages from /static."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .routes import backup, subjects, today, topics, tree

STATIC_DIR = db.ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Study App", lifespan=lifespan)
app.include_router(tree.router)
app.include_router(subjects.router)
app.include_router(topics.router)
app.include_router(today.router)
app.include_router(backup.router)

# Mounted last so /api routes take priority.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
