"""Open lectures linked to topics: MIT OpenCourseWare and other top universities' open courses.

Read-only course material from data/lectures.json (built by scripts/match_lectures.py), so it is
not stored in the database and not part of backups.
"""

import json
from functools import lru_cache

from . import db

FILE = db.ROOT / "data" / "lectures.json"
EMPTY = {"courses": {}, "subject_courses": {}, "lectures": [], "topics": {}}


@lru_cache(maxsize=1)
def _load() -> tuple[dict, dict]:
    data = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else EMPTY
    return data, {lec["id"]: lec for lec in data["lectures"]}


def for_topic(topic_id: str) -> list[dict]:
    """The lectures for a topic, best first, each with its course's name."""
    data, by_id = _load()
    out = []
    for lid in data["topics"].get(topic_id, []):
        lec = by_id.get(lid)
        if lec:
            course = data["courses"][lec["course"]]
            out.append({"title": lec["title"], "url": lec["url"], "kind": lec["kind"],
                        "course": lec["course"], "course_title": course["title"]})
    return out


def for_subject(subject_id: str) -> list[dict]:
    """The open courses a subject draws on, main course first."""
    data, _ = _load()
    return [{"code": cid, **data["courses"][cid]} for cid in data["subject_courses"].get(subject_id, [])
            if cid in data["courses"]]
