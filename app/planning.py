"""Grades and the semester plan: GPA by area, and prerequisites planned in the wrong order."""

import re

# The common 4.0 scale. Universities differ (some give A+ 4.3, or B+ 3.5), so the page says
# which scale it assumed.
LETTER_POINTS = {
    "A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7, "C+": 2.3, "C": 2.0,
    "C-": 1.7, "D+": 1.3, "D": 1.0, "D-": 0.7, "F": 0.0,
}
SCALE_TEXT = "A/A+ 4.0, A− 3.7, B+ 3.3, B 3.0, B− 2.7, C+ 2.3, C 2.0, C− 1.7, D+ 1.3, D 1.0, F 0"


def parse_grade(text: str | None) -> dict | None:
    """A letter grade (on the 4.0 scale) or a number; None for blank or unknown (e.g. "Pass")."""
    if not text or not text.strip():
        return None
    t = text.strip().upper().replace("−", "-").replace("–", "-")
    if t in LETTER_POINTS:
        return {"kind": "letter", "points": LETTER_POINTS[t]}
    try:
        value = float(t.replace(",", "."))
    except ValueError:
        return None
    return {"kind": "number", "value": value} if 0 <= value <= 100 else None


def _number_scale(values: list[float]) -> int:
    top = max(values)
    return 4 if top <= 4 else 10 if top <= 10 else 100


def _summary(graded: list[dict]) -> dict:
    letters = [g["parsed"]["points"] for g in graded if g["parsed"]["kind"] == "letter"]
    numbers = [g["parsed"]["value"] for g in graded if g["parsed"]["kind"] == "number"]
    return {
        "gpa": round(sum(letters) / len(letters), 2) if letters else None,
        "letter_count": len(letters),
        "average": round(sum(numbers) / len(numbers), 2) if numbers else None,
        "number_count": len(numbers),
        "out_of": _number_scale(numbers) if numbers else None,
    }


def grades(subjects: list[dict], lanes: list[dict]) -> dict:
    """GPA overall and by area (lane), unweighted because credits aren't recorded."""
    graded, not_counted = [], []
    for s in subjects:
        if not s.get("grade"):
            continue
        parsed = parse_grade(s["grade"])
        row = {"id": s["id"], "name": s["name"], "lane_id": s["lane_id"], "grade": s["grade"],
               "points": parsed.get("points") if parsed else None, "parsed": parsed}
        (graded if parsed else not_counted).append(row)
    by_lane = []
    for lane in lanes:
        rows = [g for g in graded if g["lane_id"] == lane["id"]]
        if rows:
            by_lane.append({"lane_id": lane["id"], "name": lane["name"], "count": len(rows), **_summary(rows)})
    clean = lambda rows: [{k: v for k, v in r.items() if k != "parsed"} for r in rows]  # noqa: E731
    return {"overall": {"count": len(graded), **_summary(graded)}, "by_lane": by_lane,
            "graded": clean(graded), "not_counted": clean(not_counted), "scale": SCALE_TEXT}


def semester_key(name: str) -> tuple:
    """Sort order for semester names like "Year 2 · Sem 1", "Y2S1", "2027 Term 1" or "Fall 2026"."""
    t = name.lower()
    m = re.search(r"y(?:ear)?\s*(\d+)\D*?(?:s(?:em(?:ester)?)?|t(?:erm)?)\s*(\d+)", t)
    if m:
        return (0, int(m.group(1)), int(m.group(2)), t)
    m = re.search(r"(\d{4})", t)
    if m:
        season = next((i for i, w in enumerate(("spring", "summer", "fall", "autumn", "winter")) if w in t), 0)
        term = re.search(r"(?:term|sem(?:ester)?|s)\s*(\d+)", t)
        return (1, int(m.group(1)), int(term.group(1)) if term else season, t)
    return (2, 0, 0, t)


def semester_plan(subjects: list[dict], relations: list[dict]) -> dict:
    """Subjects grouped by semester in order, the ones not planned yet, and order warnings."""
    by_id = {s["id"]: s for s in subjects}
    names = sorted({s["semester"] for s in subjects if s.get("semester")}, key=semester_key)
    order = {n: i for i, n in enumerate(names)}
    keep = ("id", "name", "short_name", "lane_id", "kind", "status", "state", "semester", "grade", "tier")
    pick = lambda s: {k: s.get(k) for k in keep}  # noqa: E731
    semesters = [{"name": n, "subjects": [pick(s) for s in subjects if s.get("semester") == n]} for n in names]
    unplanned = [pick(s) for s in sorted(subjects, key=lambda s: (s["tier"], s.get("grid_row", 0)))
                 if not s.get("semester") and s["status"] != "done"]

    warnings = []
    for r in relations:
        if r["kind"] != "prereq":
            continue
        pre, sub = by_id.get(r["from_id"]), by_id.get(r["to_id"])
        if not pre or not sub or not sub.get("semester") or sub["status"] == "done" or pre["status"] == "done":
            continue
        if not pre.get("semester"):
            warnings.append({"subject_id": sub["id"], "prereq_id": pre["id"], "kind": "unplanned",
                             "text": f"{sub['short_name']} is planned for {sub['semester']}, "
                                     f"but its prerequisite {pre['short_name']} isn't planned yet."})
        elif order[pre["semester"]] > order[sub["semester"]]:
            warnings.append({"subject_id": sub["id"], "prereq_id": pre["id"], "kind": "later",
                             "text": f"{sub['short_name']} is planned for {sub['semester']}, "
                                     f"before its prerequisite {pre['short_name']} ({pre['semester']})."})
        elif pre["semester"] == sub["semester"]:
            warnings.append({"subject_id": sub["id"], "prereq_id": pre["id"], "kind": "same",
                             "text": f"{sub['short_name']} and its prerequisite {pre['short_name']} "
                                     f"are both planned for {sub['semester']}."})
    return {"semesters": semesters, "unplanned": unplanned, "warnings": warnings}
