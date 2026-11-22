from fastapi.testclient import TestClient
import pytest

from app import planning


def test_parse_grade():
    assert planning.parse_grade("A-") == {"kind": "letter", "points": 3.7}
    assert planning.parse_grade(" b+ ") == {"kind": "letter", "points": 3.3}
    assert planning.parse_grade("A−") == {"kind": "letter", "points": 3.7}      # typographic minus
    assert planning.parse_grade("8,5") == {"kind": "number", "value": 8.5}
    assert planning.parse_grade("Pass") is None and planning.parse_grade("") is None
    assert planning.parse_grade("140") is None


def test_semester_order():
    names = ["Year 2 · Sem 1", "Year 1 · Sem 2", "Y1S1", "Fall 2027", "Spring 2027", "Someday"]
    assert sorted(names, key=planning.semester_key) == ["Y1S1", "Year 1 · Sem 2", "Year 2 · Sem 1",
                                                         "Spring 2027", "Fall 2027", "Someday"]


def test_grades_by_area():
    lanes = [{"id": "math", "name": "Maths"}, {"id": "prog", "name": "Programming"}]
    subjects = [{"id": "a", "name": "A", "lane_id": "math", "grade": "A"},
                {"id": "b", "name": "B", "lane_id": "math", "grade": "B"},
                {"id": "c", "name": "C", "lane_id": "prog", "grade": "8"},
                {"id": "d", "name": "D", "lane_id": "prog", "grade": "Pass"},
                {"id": "e", "name": "E", "lane_id": "prog", "grade": None}]
    g = planning.grades(subjects, lanes)
    assert g["overall"]["gpa"] == 3.5 and g["overall"]["letter_count"] == 2
    assert g["overall"]["average"] == 8 and g["overall"]["out_of"] == 10
    assert [l["lane_id"] for l in g["by_lane"]] == ["math", "prog"] and g["by_lane"][0]["gpa"] == 3.5
    assert [n["id"] for n in g["not_counted"]] == ["d"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDY_APP_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_semester_plan_warns_about_prerequisite_order(client):
    client.put("/api/progress/calc2", json={"status": "not_started", "semester": "Year 1 · Sem 2"})
    client.put("/api/progress/mvc", json={"status": "not_started", "semester": "Year 1 · Sem 1"})
    client.put("/api/progress/linalg", json={"status": "in_progress", "semester": "Year 1 · Sem 1", "grade": "B+"})
    d = client.get("/api/planning").json()
    assert [s["name"] for s in d["semesters"]] == ["Year 1 · Sem 1", "Year 1 · Sem 2"]
    later = [w for w in d["warnings"] if w["kind"] == "later"]
    assert any(w["subject_id"] == "mvc" and w["prereq_id"] == "calc2" for w in later)
    assert all(s["semester"] is None for s in d["unplanned"])
    assert d["grades"]["overall"]["gpa"] == 3.3

    client.put("/api/progress/mvc", json={"status": "not_started", "semester": "Year 2 · Sem 1"})
    d = client.get("/api/planning").json()
    assert not [w for w in d["warnings"] if w["subject_id"] == "mvc" and w["prereq_id"] == "calc2"]
