import pytest
from fastapi.testclient import TestClient

from app import db, logic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDY_APP_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:  # runs startup, which creates and seeds the database
        yield c


# ---- Curriculum data ----

def test_curriculum_has_43_courses_and_7_gap_fillers():
    subjects = db.load_curriculum()["subjects"]
    assert sum(s["kind"] == "course" for s in subjects) == 43
    assert sum(s["kind"] == "gap_filler" for s in subjects) == 7


def test_every_relation_points_to_a_real_subject():
    subjects = db.load_curriculum()["subjects"]
    ids = {s["id"] for s in subjects}
    for s in subjects:
        for other in s["prereqs"] + s["related"] + s["supports"]:
            assert other in ids, f"{s['id']} refers to unknown subject {other}"


def test_prerequisites_never_sit_in_a_later_tier():
    subjects = {s["id"]: s for s in db.load_curriculum()["subjects"]}
    for s in subjects.values():
        for p in s["prereqs"]:
            assert subjects[p]["tier"] <= s["tier"], f"{p} should not be to the right of {s['id']}"


def test_no_two_subjects_share_a_grid_cell():
    cells = [(s["tier"], s["row"]) for s in db.load_curriculum()["subjects"]]
    assert len(cells) == len(set(cells))


def test_prerequisites_have_no_cycles():
    rels = [{"from_id": p, "to_id": s["id"], "kind": "prereq"}
            for s in db.load_curriculum()["subjects"] for p in s["prereqs"]]
    assert logic.find_cycle(rels) is None


# ---- Unlock rules ----

def _subjects(**statuses):
    kinds = {"python": "gap_filler"}
    return {sid: {"kind": kinds.get(sid, "course"), "status": st} for sid, st in statuses.items()}


def test_states_follow_prerequisites():
    rels = [{"from_id": "a", "to_id": "b", "kind": "prereq"}]
    states = logic.compute_states(_subjects(a="not_started", b="not_started"), rels)
    assert states == {"a": "ready", "b": "locked"}
    states = logic.compute_states(_subjects(a="done", b="not_started"), rels)
    assert states == {"a": "done", "b": "ready"}


def test_gap_filler_never_blocks_a_course():
    rels = [{"from_id": "python", "to_id": "sci", "kind": "prereq"}]
    states = logic.compute_states(_subjects(python="not_started", sci="not_started"), rels)
    assert states["sci"] == "ready"


def test_find_cycle_reports_a_loop():
    rels = [{"from_id": x, "to_id": y, "kind": "prereq"} for x, y in [("a", "b"), ("b", "c"), ("c", "a")]]
    assert logic.find_cycle(rels) is not None


# ---- API ----

def test_tree_endpoint_returns_everything(client):
    data = client.get("/api/tree").json()
    assert len(data["lanes"]) == 7
    assert len(data["subjects"]) == 50
    states = {s["id"]: s["state"] for s in data["subjects"]}
    assert states["calc1"] == "ready"
    assert states["calc2"] == "locked"


def test_marking_done_unlocks_next_subjects_and_persists(client):
    res = client.put("/api/progress/cintro", json={"status": "done", "semester": "Year 1 · Sem 1", "grade": "A"})
    assert res.status_code == 200
    assert set(res.json()["unlocked"]) == {"clang", "python"}

    subjects = {s["id"]: s for s in client.get("/api/tree").json()["subjects"]}
    assert subjects["cintro"]["state"] == "done"
    assert subjects["cintro"]["grade"] == "A"
    assert subjects["clang"]["state"] == "ready"


def test_blank_semester_and_grade_are_stored_as_empty(client):
    client.put("/api/progress/calc1", json={"status": "in_progress", "semester": "  ", "grade": ""})
    calc1 = next(s for s in client.get("/api/tree").json()["subjects"] if s["id"] == "calc1")
    assert calc1["semester"] is None and calc1["grade"] is None


def test_unknown_subject_returns_404(client):
    assert client.put("/api/progress/nope", json={"status": "done"}).status_code == 404


def test_invalid_status_is_rejected(client):
    assert client.put("/api/progress/calc1", json={"status": "finished"}).status_code == 422


def test_reseeding_keeps_progress(client):
    client.put("/api/progress/linalg", json={"status": "done"})
    db.init_db()
    linalg = next(s for s in client.get("/api/tree").json()["subjects"] if s["id"] == "linalg")
    assert linalg["status"] == "done"


def test_pages_are_served(client):
    home = client.get("/")
    assert home.status_code == 200 and "<title>Today" in home.text
    tree = client.get("/tree.html")
    assert tree.status_code == 200 and "Skill Tree" in tree.text
    assert client.get("/subject.html").status_code == 200
