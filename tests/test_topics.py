from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db, logic


@pytest.fixture()
def clock(monkeypatch):
    """A controllable 'today' for the API."""
    from app import clock

    current = {"day": date(2026, 11, 19)}
    monkeypatch.setattr(clock, "today", lambda: current["day"])
    return current


@pytest.fixture()
def client(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("STUDY_APP_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


def dashboard(client, subject_id="linalg"):
    res = client.get(f"/api/subjects/{subject_id}/dashboard")
    assert res.status_code == 200
    return res.json()


# ---- Topic data ----

def test_every_subject_has_topics_and_ids_are_unique():
    subject_ids = {s["id"] for s in db.load_curriculum()["subjects"]}
    topics = db.load_topics()
    assert set(topics) == subject_ids
    for sid, units in topics.items():
        _, rows = db.parse_topics(sid, units)
        ids = [r["id"] for r in rows]
        assert len(ids) == len(set(ids)), f"duplicate topic in {sid}"
        assert len(rows) >= 5, f"{sid} has too few topics"


def test_star_marks_ai_key_topics():
    _, rows = db.parse_topics("x", [["Unit", ["Plain", "*Starred"]]])
    assert [(r["name"], r["ai_key"]) for r in rows] == [("Plain", 0), ("Starred", 1)]


# ---- Rules ----

def test_mastery_pct_and_level_counts():
    assert logic.mastery_pct([]) == 0
    assert logic.mastery_pct([4, 4]) == 100
    assert logic.mastery_pct([0, 2]) == 25
    assert logic.level_counts([0, 1, 1, 4]) == [1, 2, 0, 0, 1]


def test_review_interval_grows_with_mastery():
    d = date(2026, 1, 1)
    assert logic.next_review(0, d) is None
    gaps = [(logic.next_review(level, d) - d).days for level in range(1, 5)]
    assert gaps == sorted(gaps) and len(set(gaps)) == 4


def test_weekly_counts_buckets_by_monday():
    today = date(2026, 11, 19)  # a Thursday
    weeks = logic.weekly_counts([date(2026, 11, 16), date(2026, 11, 19), date(2026, 11, 9)], today, weeks=3)
    assert [w["week_start"] for w in weeks] == ["2026-11-02", "2026-11-09", "2026-11-16"]
    assert [w["count"] for w in weeks] == [0, 1, 2]


# ---- API ----

def test_dashboard_lists_units_and_topics(client):
    data = dashboard(client)
    assert data["subject"]["name"] == "Linear Algebra"
    assert len(data["units"]) == 6
    assert data["summary"]["topic_count"] == sum(u["topic_count"] for u in data["units"])
    assert data["summary"]["ai_key_count"] > 0
    assert data["summary"]["mastery_pct"] == 0


def test_setting_mastery_updates_summary_and_starts_subject(client):
    res = client.put("/api/topics/linalg:eigenvalues-and-eigenvectors", json={"mastery": 3})
    assert res.status_code == 200
    assert res.json()["subject_started"] is True
    assert res.json()["topic"]["last_reviewed"] == "2026-11-19"

    data = dashboard(client)
    assert data["summary"]["started"] == 1
    assert data["subject"]["status"] == "in_progress"
    assert data["activity"]["weeks"][-1]["count"] == 1


def test_topic_comes_due_and_review_resets_it(client, clock):
    client.put("/api/topics/linalg:determinants", json={"mastery": 1})
    assert dashboard(client)["summary"]["due_count"] == 0

    clock["day"] = date(2026, 11, 22)  # 3 days later; Learning comes due after 2
    data = dashboard(client)
    assert [t["name"] for t in data["review_queue"]] == ["Determinants"]

    client.put("/api/topics/linalg:determinants", json={"reviewed": True})
    assert dashboard(client)["summary"]["due_count"] == 0


def test_reviewing_an_unstarted_topic_starts_it(client):
    res = client.put("/api/topics/linalg:rank", json={"reviewed": True})
    assert res.json()["topic"]["mastery"] == 1


def test_notes_are_saved_and_blank_notes_clear(client):
    client.put("/api/topics/linalg:rank", json={"notes": "rank = number of pivots"})
    topic = next(t for u in dashboard(client)["units"] for t in u["topics"] if t["id"] == "linalg:rank")
    assert topic["notes"] == "rank = number of pivots"
    client.put("/api/topics/linalg:rank", json={"notes": "   "})
    topic = next(t for u in dashboard(client)["units"] for t in u["topics"] if t["id"] == "linalg:rank")
    assert topic["notes"] is None


def test_tree_reports_topic_mastery(client):
    client.put("/api/topics/linalg:rank", json={"mastery": 4})
    linalg = next(s for s in client.get("/api/tree").json()["subjects"] if s["id"] == "linalg")
    assert linalg["topic_count"] > 0
    assert linalg["mastery_pct"] == round(100 * 4 / (4 * linalg["topic_count"]))


def test_bad_topic_requests(client):
    assert client.put("/api/topics/nope", json={"mastery": 1}).status_code == 404
    assert client.put("/api/topics/linalg:rank", json={"mastery": 7}).status_code == 422
    assert client.get("/api/subjects/nope/dashboard").status_code == 404


def test_reseeding_keeps_topic_progress(client):
    client.put("/api/topics/linalg:rank", json={"mastery": 2})
    db.init_db()
    topic = next(t for u in dashboard(client)["units"] for t in u["topics"] if t["id"] == "linalg:rank")
    assert topic["mastery"] == 2


def test_review_session_list_and_rating(client, clock):
    client.put("/api/topics/linalg:rank", json={"mastery": 1})
    client.put("/api/topics/linalg:determinants", json={"mastery": 2, "notes": "det(AB) = det(A) det(B)"})
    clock["day"] = date(2026, 11, 25)
    data = client.get("/api/subjects/linalg/review").json()
    assert [t["id"] for t in data["topics"]] == ["linalg:rank", "linalg:determinants"]   # most overdue first
    assert data["topics"][1]["notes"].startswith("det")
    # Rating a topic at the same level still counts as a review and restarts its clock.
    client.put("/api/topics/linalg:rank", json={"mastery": 1, "reviewed": True})
    assert [t["id"] for t in client.get("/api/subjects/linalg/review").json()["topics"]] == ["linalg:determinants"]
    recent = dashboard(client)["activity"]["recent"]
    assert recent[0]["kind"] == "review"


def test_topics_link_open_lectures(client):
    d = client.get("/api/subjects/linalg/dashboard").json()
    rank = next(t for u in d["units"] for t in u["topics"] if t["id"] == "linalg:rank")
    assert rank["lectures"] and rank["lectures"][0]["url"].startswith("https://ocw.mit.edu/courses/18-06")
    assert rank["lectures"][0]["course_title"].startswith("MIT 18.06")
    assert d["courses"][0]["code"] == "18.06"
    assert all(t["lectures"] == [] or t["lectures"][0]["title"] for u in d["units"] for t in u["topics"])


def test_lecture_data_is_consistent():
    import json
    from app import db
    data = json.loads((db.ROOT / "data" / "lectures.json").read_text(encoding="utf-8"))
    ids = {lec["id"] for lec in data["lectures"]}
    known = {f"{sid}:{db.slugify(n.lstrip('*').strip())}" for sid, units in db.load_topics().items() for _, names in units for n in names}
    for topic_id, refs in data["topics"].items():
        assert topic_id in known, topic_id
        assert refs and set(refs) <= ids, topic_id
    for lec in data["lectures"]:
        assert lec["url"].startswith("https://") and lec["course"] in data["courses"]
    assert len(data["topics"]) > 500
