from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db, logic, study_store


@pytest.fixture()
def clock(monkeypatch):
    from app import clock as clock_module

    current = {"day": date(2026, 11, 19)}  # a Thursday
    monkeypatch.setattr(clock_module, "today", lambda: current["day"])
    return current


@pytest.fixture()
def client(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("STUDY_APP_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


def dash(client, subject_id="linalg"):
    res = client.get(f"/api/subjects/{subject_id}/dashboard")
    assert res.status_code == 200, res.text
    return res.json()


def topic(data, topic_id):
    return next(t for u in data["units"] for t in u["topics"] if t["id"] == topic_id)


# ---- Rules ----

def test_card_due_dates(client):
    card_id = client.post("/api/topics/linalg:rank/cards", json={"front": "Q", "back": "A"}).json()["id"]
    res = client.post(f"/api/cards/{card_id}/review", json={"result": "good"}).json()   # box 1 -> 1 day
    assert res["due_on"] == "2026-11-20"
    res = client.post(f"/api/cards/{card_id}/review", json={"result": "easy"}).json()   # box 3 -> 7 days
    assert res["due_on"] == "2026-11-26"


def test_leitner_boxes():
    assert logic.next_box(0, "good") == 1
    assert logic.next_box(3, "good") == 4
    assert logic.next_box(4, "good") == 4
    assert logic.next_box(1, "easy") == 3
    assert logic.next_box(4, "again") == 1
    assert logic.next_box(0, "hard") == 1
    assert logic.mastery_from_cards([]) is None
    assert logic.mastery_from_cards([4, 4, 2]) == 3


def test_review_queue_puts_exam_topics_first():
    t = lambda id, due, days, m: {"id": id, "name": id, "is_due": due, "days_until_review": days, "mastery": m}
    topics = [t("a", True, -9, 2), t("b", True, -1, 2), t("c", False, 5, 1), t("d", False, 5, 4)]
    queue = logic.review_queue(topics, exam_topic_ids={"b", "c", "d"})
    assert [(q["id"], q["reason"]) for q in queue] == [("b", "due"), ("a", "due"), ("c", "exam_prep")]


def test_weak_spot_scoring():
    assert logic.weak_spot(0, 0) == (0, [])
    assert logic.weak_spot(0, 1)[0] < logic.WEAK_THRESHOLD          # one miss isn't a pattern
    score, reasons = logic.weak_spot(1, 2, struggled_on_paper=True)
    assert score == 3 + 4 + 4
    assert reasons == ["went badly on a past paper", "marked down once", "missed 2 flashcards"]


def test_topic_links_all_resolve(client):
    # Startup raises if any link names a missing topic; check a known link is present.
    links = study_store.load_topic_links()
    assert {"from_topic": "dsp:convolution", "to_topic": "dl:convolution-and-pooling"} in [
        {k: l[k] for k in ("from_topic", "to_topic")} for l in links]


# ---- Exams ----

def test_exam_readiness_and_exam_prep(client):
    units = [u["id"] for u in dash(client)["units"]]
    res = client.post("/api/subjects/linalg/exams", json={"name": "Midterm", "exam_date": "2026-12-01", "unit_ids": units[:2]})
    assert res.status_code == 201

    data = dash(client)
    nxt = data["summary"]["next_exam"]
    assert nxt["name"] == "Midterm" and nxt["days_left"] == 12 and nxt["readiness_pct"] == 0
    prep = [q for q in data["review_queue"] if q["reason"] == "exam_prep"]
    assert prep and all(q["unit_id"] in units[:2] for q in prep)

    first_topic = data["units"][0]["topics"][0]["id"]
    client.put(f"/api/topics/{first_topic}", json={"mastery": 4})
    assert dash(client)["summary"]["next_exam"]["readiness_pct"] > 0

    client.delete(f"/api/exams/{nxt['id']}")
    assert dash(client)["exams"] == []


def test_exam_rejects_units_from_another_subject(client):
    res = client.post("/api/subjects/linalg/exams", json={"name": "X", "exam_date": "2026-12-01", "unit_ids": ["prob:u1"]})
    assert res.status_code == 422


def test_exam_with_no_units_covers_whole_subject(client):
    client.post("/api/subjects/linalg/exams", json={"name": "Final", "exam_date": "2027-01-10"})
    exam = dash(client)["exams"][0]
    assert exam["topic_count"] == dash(client)["summary"]["topic_count"]


# ---- Study sessions ----

def test_study_session_logs_minutes_and_starts_topic(client):
    res = client.post("/api/topics/linalg:rank/sessions", json={"minutes": 25})
    assert res.status_code == 201 and res.json()["mastery"] == 1
    data = dash(client)
    assert data["summary"]["minutes_this_week"] == 25
    assert data["activity"]["weeks"][-1]["minutes"] == 25
    assert topic(data, "linalg:rank")["minutes"] == 25
    assert client.get("/api/overview").json()["minutes_this_week"] == 25


def test_session_length_is_validated(client):
    assert client.post("/api/topics/linalg:rank/sessions", json={"minutes": 0}).status_code == 422


# ---- Flashcards ----

def test_flashcard_practice_sets_topic_mastery(client):
    ids = [client.post("/api/topics/linalg:rank/cards", json={"front": f"Q{i}", "back": "A"}).json()["id"] for i in range(2)]
    assert len(topic(dash(client), "linalg:rank")["cards"]) == 2

    cards = client.get("/api/subjects/linalg/practice", params={"topic_id": "linalg:rank"}).json()["cards"]
    assert [c["id"] for c in cards] == ids

    for card_id in ids:
        client.post(f"/api/cards/{card_id}/review", json={"result": "easy"})   # box 0 -> 2
    t = topic(dash(client), "linalg:rank")
    assert t["mastery"] == 2 and t["last_reviewed"] == "2026-11-19"

    res = client.post(f"/api/cards/{ids[0]}/review", json={"result": "again"})  # boxes 1 and 2 -> mastery 2
    assert res.json()["box"] == 1


def test_missed_flashcards_make_a_weak_spot(client):
    card_id = client.post("/api/topics/linalg:rank/cards", json={"front": "Q", "back": "A"}).json()["id"]
    for _ in range(2):
        client.post(f"/api/cards/{card_id}/review", json={"result": "again"})
    weak = dash(client)["weak_spots"]
    assert weak[0]["id"] == "linalg:rank" and "missed 2 flashcards" in weak[0]["weak_reasons"]
    overview = client.get("/api/overview").json()
    assert overview["weak_spots"][0]["id"] == "linalg:rank"


def test_marking_down_makes_a_weak_spot(client):
    client.put("/api/topics/linalg:rank", json={"mastery": 3})
    client.put("/api/topics/linalg:rank", json={"mastery": 1})
    assert "marked down once" in topic(dash(client), "linalg:rank")["weak_reasons"]


def test_card_edit_delete_and_validation(client):
    card_id = client.post("/api/topics/linalg:rank/cards", json={"front": "Q", "back": "A"}).json()["id"]
    assert client.put(f"/api/cards/{card_id}", json={"front": "Q2", "back": "A2"}).status_code == 200
    assert topic(dash(client), "linalg:rank")["cards"][0]["front"] == "Q2"
    assert client.post(f"/api/cards/{card_id}/review", json={"result": "maybe"}).status_code == 422
    assert client.delete(f"/api/cards/{card_id}").status_code == 204
    assert client.delete(f"/api/cards/{card_id}").status_code == 404


# ---- Resources ----

def test_resources(client):
    res = client.post("/api/topics/linalg:rank/resources",
                      json={"title": "Strang lecture 9", "url": "https://ocw.mit.edu/x", "kind": "video"})
    assert res.status_code == 201
    assert topic(dash(client), "linalg:rank")["resources"][0]["title"] == "Strang lecture 9"
    bad = client.post("/api/topics/linalg:rank/resources", json={"title": "x", "url": "javascript:alert(1)"})
    assert bad.status_code == 422
    assert client.delete(f"/api/resources/{res.json()['id']}").status_code == 204


# ---- Topic links ----

def test_dashboard_shows_links_both_ways(client):
    svd = topic(dash(client, "linalg"), "linalg:singular-value-decomposition-svd")
    assert any(l["topic_id"] == "ml:pca" for l in svd["links_out"])
    pca = topic(dash(client, "ml"), "ml:pca")
    assert any(l["topic_id"] == "linalg:singular-value-decomposition-svd" for l in pca["links_in"])


# ---- Practice exams ----

def test_practice_exam_catalog_is_valid(client):
    # Startup raises on unknown subjects, bad unit numbers, non-https links or duplicates.
    with db.connect() as conn:
        exams = study_store.load_practice_exams(conn)
    assert len(exams) >= 80
    assert all(e["unit_ids"] for e in exams)
    assert any(e["kind"] == "final" for e in exams)


def test_practice_exams_show_on_dashboard_and_topics(client):
    data = dash(client)
    exams = data["practice_exams"]
    assert data["summary"]["practice_total"] == len(exams) > 0
    finals = [e for e in exams if e["end_of_subject"]]
    assert finals and all(f["kind"] == "final" for f in finals)
    # A topic in the first unit lists the exams that cover that unit.
    first = data["units"][0]["topics"][0]
    covering = {e["id"] for e in exams if data["units"][0]["id"] in e["unit_ids"]}
    assert set(first["practice_exam_ids"]) == covering and covering


def test_ticking_practice_exams(client, clock):
    exam = dash(client)["practice_exams"][0]
    res = client.put(f"/api/practice-exams/{exam['id']}", json={"done": True})
    assert res.status_code == 200 and res.json()["done_on"] == "2026-11-19"
    data = dash(client)
    assert data["summary"]["practice_done"] == 1
    assert data["practice_exams"][0]["done"] is True
    assert client.get("/api/overview").json()["practice_done"] == 1

    client.put(f"/api/practice-exams/{exam['id']}", json={"done": False})
    assert dash(client)["summary"]["practice_done"] == 0


def test_practice_ticks_survive_reloading_the_catalog(client):
    exam_id = dash(client)["practice_exams"][0]["id"]
    client.put(f"/api/practice-exams/{exam_id}", json={"done": True})
    db.init_db()
    assert dash(client)["practice_exams"][0]["done"] is True


def test_unknown_practice_exam(client):
    assert client.put("/api/practice-exams/nope", json={"done": True}).status_code == 404
