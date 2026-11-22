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
    clock["day"] = date(2026, 11, 22)   # Learning comes due after 2 days; a new day builds a new plan
    plan = today(client)["plan"]
    kinds = [i["kind"] for i in plan]
    assert kinds[0] == "review" and plan[0]["topic_id"] == "linalg:rank"
    assert "exam_prep" in kinds and "practice" in kinds and "cards" in kinds
    practice = next(i for i in plan if i["kind"] == "practice")
    assert practice["url"].startswith("https://") and practice["subject_id"] == "linalg"


def test_final_week_suggests_end_of_subject_exam(client):
    client.post("/api/subjects/linalg/exams", json={"name": "Final", "exam_date": "2026-11-23"})
    client.post("/api/today/rebuild")
    practice = next(i for i in today(client)["plan"] if i["kind"] == "practice")
    assert "Final" in practice["title"]


def test_ticking_does_the_real_action(client):
    item = today(client)["plan"][0]                      # "Start Calculus I: ..."
    assert item["kind"] == "new"
    assert client.put(f"/api/today/ticks/{item['key']}", json={"done": True}).status_code == 200
    data = today(client)
    assert data["plan"][0]["done"] is True
    assert data["planned_minutes"] == sum(i["minutes"] for i in data["plan"] if not i["done"])
    assert data["streak_days"] == 1 and data["studied_today"] is True
    topic = client.get("/api/subjects/calc1/dashboard").json()["units"][0]["topics"][0]
    assert topic["id"] == item["topic_id"] and topic["mastery"] == 1   # the topic really started


def test_plan_stays_fixed_and_completes_from_real_actions(client):
    first = [i["key"] for i in today(client)["plan"]]
    item = today(client)["plan"][1]
    client.put(f"/api/topics/{item['topic_id']}", json={"mastery": 2})  # study it on the subject page
    data = today(client)
    assert [i["key"] for i in data["plan"]] == first                 # no reshuffle
    assert data["plan"][1]["done"] is True


def test_ticking_a_past_paper_ticks_the_paper(client):
    client.put("/api/progress/linalg", json={"status": "in_progress"})
    client.post("/api/today/rebuild")
    paper = next(i for i in today(client)["plan"] if i["kind"] == "practice")
    client.put(f"/api/today/ticks/{paper['key']}", json={"done": True})
    exams = client.get("/api/subjects/linalg/dashboard").json()["practice_exams"]
    assert next(e for e in exams if e["id"] == paper["exam_id"])["done"] is True
    client.put(f"/api/today/ticks/{paper['key']}", json={"done": False})
    exams = client.get("/api/subjects/linalg/dashboard").json()["practice_exams"]
    assert next(e for e in exams if e["id"] == paper["exam_id"])["done"] is False


def test_ticking_reviews_marks_topics_reviewed(client, clock):
    client.put("/api/topics/linalg:rank", json={"mastery": 1})
    client.put("/api/topics/linalg:determinants", json={"mastery": 1})
    clock["day"] = date(2026, 11, 22)
    review = today(client)["plan"][0]
    assert review["kind"] == "review" and review["count"] == 2
    client.put(f"/api/today/ticks/{review['key']}", json={"done": True})
    dash = client.get("/api/subjects/linalg/dashboard").json()
    assert dash["summary"]["due_count"] == 0


def test_add_more_and_rebuild(client):
    before = today(client)["plan"]
    assert client.post("/api/today/more").json()["added"] > 0
    after = today(client)["plan"]
    assert [i["key"] for i in after[:len(before)]] == [i["key"] for i in before]
    assert len({i["key"] for i in after}) == len(after)                # no duplicates
    client.put(f"/api/today/ticks/{before[0]['key']}", json={"done": True})
    client.post("/api/today/rebuild")
    rebuilt = today(client)["plan"]
    assert rebuilt[0]["key"] == before[0]["key"] and rebuilt[0]["done"]   # done items kept


def test_unknown_plan_item(client):
    assert client.put("/api/today/ticks/nope", json={"done": True}).status_code == 404


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
