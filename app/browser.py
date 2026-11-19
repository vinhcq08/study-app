"""Runs the app's API inside the browser with Pyodide, for the GitHub Pages version.

The same routes, database code and rules run here as on the server. Requests come from
static/js/browser-backend.js instead of over HTTP, and the SQLite database lives in the
browser's storage (IndexedDB), mounted at DATA_DIR by the loader.
"""

import os
from urllib.parse import unquote

import fastapi.dependencies.utils
import fastapi.routing

DATA_DIR = "/study-app-data"
os.environ.setdefault("STUDY_APP_DB", f"{DATA_DIR}/study.db")


async def _call_inline(func, *args, **kwargs):
    """Browsers have no threads, so run FastAPI's normal (sync) handlers directly."""
    return func(*args, **kwargs)


fastapi.routing.run_in_threadpool = _call_inline
fastapi.dependencies.utils.run_in_threadpool = _call_inline

from fastapi import FastAPI  # noqa: E402  (after the patch above)

from . import db  # noqa: E402
from .routes import subjects, today, topics, tree  # noqa: E402

api = FastAPI(title="Study App (browser)")
for module in (tree, subjects, topics, today):
    api.include_router(module.router)


def start() -> None:
    """Create or upgrade the database and load the curriculum. Your progress is kept."""
    db.init_db()


async def handle(method: str, url: str, body: str = "") -> tuple[int, str]:
    """Run one API request and return (status, response body)."""
    path, _, query = url.partition("?")
    data = (body or "").encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "https",
        "path": unquote(path),
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())],
        "server": ("browser", 443),
        "client": ("browser", 0),
    }
    pending = [{"type": "http.request", "body": data, "more_body": False}]
    status = 500
    chunks: list[bytes] = []

    async def receive():
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await api(scope, receive, send)
    return status, b"".join(chunks).decode()
