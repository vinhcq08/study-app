from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import logic


@pytest.fixture()
def clock(monkeypatch):
    from app import clock as clock_module

    current = {"day": date(2026, 11, 19)}
    monkeypatch.setattr(clock_module, "today", lambda: current["day"])
    return current


@pytest.fixture()
def client(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("STUDY_APP_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


def today(client):
    res = client.get("/api/today")
    assert res.status_code == 200, res.text
    return res.json()


# ---- Rules ----

def test_subject_levels():
    assert logic.subject_level(0) == (1, 20)
    assert logic.subject_level(42) == (3, 60)
    assert logic.subject_level(100) == (5, None)


def test_streak_counts_consecutive_days():
    d = date(2026, 11, 19)
    days = {date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19)}
    assert logic.streak(days, d) == 3
    assert logic.streak(days - {d}, d) == 2          # nothing yet today: streak still alive
    assert logic.streak({date(2026, 11, 16)}, d) == 0


# ---- Plan ----

def test_fresh_start_suggests_starting_subjects(client):
    data = today(client)
    kinds = [i["kind"] for i in data["plan"]]
    assert kinds and set(kinds) == {"new"}
    assert data["plan"][0]["title"].startswith("Start ")
    assert data["streak_days"] == 0 and data["planned_minutes"] == 25 * len(kinds)


def test_plan_includes_reviews_exam_prep_practice_and_cards(client, clock):
    client.put("/api/topics/linalg:rank", json={"mastery": 1})
    client.post("/api/topics/linalg:rank/cards", json={"front": "Q", "back": "A"})
    client.post("/api/subjects/linalg/exams", json={"name": "Midterm", "exam_date": "2026-12-01"})
    clock["day"] = date(2026, 11, 22)   # Learning comes due after 2 days
    plan = today(client)["plan"]
    kinds = [i["kind"] for i in plan]
    assert kinds[0] == "review" and plan[0]["topic_id"] == "linalg:rank"
    assert "exam_prep" in kinds and "practice" in kinds and "cards" in kinds
    practice = next(i for i in plan if i["kind"] == "practice")
    assert practice["url"].startswith("https://") and practice["subject_id"] == "linalg"


def test_final_week_suggests_end_of_subject_exam(client):
    client.post("/api/subjects/linalg/exams", json={"name": "Final", "exam_date": "2026-11-23"})
    practice = next(i for i in today(client)["plan"] if i["kind"] == "practice")
    assert "Final" in practice["title"]


def test_ticking_plan_items_and_streak(client):
    item = today(client)["plan"][0]
    assert client.put(f"/api/today/ticks/{item['key']}", json={"done": True}).status_code == 200
    data = today(client)
    assert data["plan"][0]["done"] is True
    assert data["planned_minutes"] == sum(i["minutes"] for i in data["plan"] if not i["done"])
    assert data["streak_days"] == 1 and data["studied_today"] is True
    client.put(f"/api/today/ticks/{item['key']}", json={"done": False})
    assert today(client)["plan"][0]["done"] is False


def test_week_minutes_and_subject_levels(client):
    client.post("/api/topics/linalg:rank/sessions", json={"minutes": 25})
    data = today(client)
    assert data["studied_today_minutes"] == 25
    assert next(d for d in data["week"] if d["is_today"])["minutes"] == 25
    linalg = next(s for s in data["subjects"] if s["id"] == "linalg")
    assert linalg["level"] == 1


def test_tree_reports_level_due_and_practice(client):
    s = next(s for s in client.get("/api/tree").json()["subjects"] if s["id"] == "linalg")
    assert s["level"] == 1 and s["due_count"] == 0 and s["practice_total"] > 0
