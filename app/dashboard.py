"""Builds the subject dashboard and the cross-subject overview from stored data."""

from collections import defaultdict
from datetime import date, timedelta

from . import db, logic, study_store

ACTIVITY_WEEKS = 12
MARK_DOWN_WINDOW = timedelta(days=60)
MISSED_CARD_WINDOW = timedelta(days=30)


def topic_view(t: dict, now: date) -> dict:
    """A topic with its review schedule worked out."""
    last = date.fromisoformat(t["last_reviewed"]) if t["last_reviewed"] else None
    due = logic.next_review(t["mastery"], last)
    return {
        "id": t["id"],
        "unit_id": t["unit_id"],
        "name": t["name"],
        "ai_key": bool(t["ai_key"]),
        "mastery": t["mastery"],
        "notes": t["notes"],
        "last_reviewed": t["last_reviewed"],
        "next_review": due.isoformat() if due else None,
        "days_until_review": (due - now).days if due else None,
        "is_due": bool(due and due <= now),
    }


def readiness(conn, unit_ids: list[str]) -> tuple[int, int]:
    """Mastery % and topic count across the units an exam covers."""
    if not unit_ids:
        return 0, 0
    marks = ",".join("?" * len(unit_ids))
    levels = [r[0] for r in conn.execute(
        f"""SELECT COALESCE(p.mastery, 0) FROM topics t LEFT JOIN topic_progress p ON p.topic_id = t.id
            WHERE t.retired = 0 AND t.unit_id IN ({marks})""", unit_ids)]
    return logic.mastery_pct(levels), len(levels)


def exam_view(conn, exam: dict, now: date, unit_names: dict[str, str] | None = None) -> dict:
    pct, count = readiness(conn, exam["unit_ids"])
    days_left = (date.fromisoformat(exam["exam_date"]) - now).days
    view = {**exam, "days_left": days_left, "past": days_left < 0, "readiness_pct": pct, "topic_count": count}
    if unit_names is not None:
        view["unit_names"] = [unit_names[u] for u in exam["unit_ids"] if u in unit_names]
    return view


def _weak_list(topics: list[dict], marks: dict, missed: dict, weak_units: set | None = None) -> list[dict]:
    weak = []
    for t in topics:
        on_paper = bool(weak_units) and t.get("unit_id") in weak_units and t.get("mastery", 0) < logic.EXAM_PREP_BELOW
        score, reasons = logic.weak_spot(marks.get(t["id"], 0), missed.get(t["id"], 0), on_paper)
        if score >= logic.WEAK_THRESHOLD:
            weak.append({**t, "weak_score": score, "weak_reasons": reasons})
    return sorted(weak, key=lambda t: -t["weak_score"])


def build_dashboard(conn, subject_id: str, now: date) -> dict:
    lanes = {l["id"]: l for l in db.fetch_lanes(conn)}
    subjects = {s["id"]: s for s in db.fetch_subjects(conn)}
    relations = db.fetch_relations(conn)
    states = logic.compute_states(subjects, relations)
    mastery_all = db.mastery_by_subject(conn)
    units = db.fetch_units(conn, subject_id)
    unit_names = {u["id"]: u["name"] for u in units}

    since = (logic.week_start(now) - timedelta(weeks=ACTIVITY_WEEKS - 1)).isoformat()
    activity = db.fetch_activity(conn, subject_id, since)
    sessions = study_store.fetch_sessions(conn, subject_id, since)
    review_days = study_store.card_review_days(conn, subject_id, since)
    minutes = study_store.minutes_by_topic(conn, subject_id)
    marks = study_store.mark_downs(conn, (now - MARK_DOWN_WINDOW).isoformat(), subject_id)
    missed = study_store.missed_cards(conn, (now - MISSED_CARD_WINDOW).isoformat(), subject_id)

    cards = defaultdict(list)
    for c in study_store.fetch_cards_for_subject(conn, subject_id):
        cards[c["topic_id"]].append({k: c[k] for k in ("id", "front", "back", "box", "last_result", "source")})
    resources = defaultdict(list)
    for r in study_store.fetch_resources_for_subject(conn, subject_id):
        resources[r["topic_id"]].append({k: r[k] for k in ("id", "title", "url", "kind")})
    links_in, links_out = defaultdict(list), defaultdict(list)
    for l in study_store.fetch_links_for_subject(conn, subject_id):
        links_out[l["from_topic"]].append({"topic_id": l["to_topic"], "topic_name": l["to_name"],
                                           "subject_id": l["to_subject"], "subject_name": l["to_subject_name"], "why": l["why"]})
        links_in[l["to_topic"]].append({"topic_id": l["from_topic"], "topic_name": l["from_name"],
                                        "subject_id": l["from_subject"], "subject_name": l["from_subject_name"], "why": l["why"]})

    topics = []
    for t in db.fetch_topics(conn, subject_id):
        v = topic_view(t, now)
        v.update({
            "unit_name": unit_names.get(t["unit_id"], ""),
            "cards": cards[t["id"]],
            "resources": resources[t["id"]],
            "links_in": links_in[t["id"]],
            "links_out": links_out[t["id"]],
            "minutes": minutes.get(t["id"], 0),
        })
        topics.append(v)

    # Exams, and the topics the next one covers
    exams = [exam_view(conn, e, now, unit_names) for e in study_store.fetch_exams(conn, subject_id)]
    upcoming = [e for e in exams if not e["past"]]
    nxt = upcoming[0] if upcoming else None
    exam_scope = set()
    if nxt and nxt["days_left"] <= logic.EXAM_PREP_DAYS:
        scope_units = set(nxt["unit_ids"])
        exam_scope = {t["id"] for t in topics if t["unit_id"] in scope_units}
    for t in topics:
        t["on_next_exam"] = t["id"] in exam_scope

    practice = study_store.fetch_practice_exams(conn, subject_id)
    for e in practice:
        e["done"] = e["done_on"] is not None
        e["end_of_subject"] = e["kind"] == "final"
        e["covers_all"] = set(e["unit_ids"]) == set(unit_names)
        e["unit_names"] = [unit_names[u] for u in e["unit_ids"] if u in unit_names]
    for t in topics:
        t["practice_exam_ids"] = [e["id"] for e in practice if t["unit_id"] in e["unit_ids"]]

    paper_units = study_store.weak_paper_units(conn, (now - MARK_DOWN_WINDOW).isoformat(), subject_id)
    weak = _weak_list(topics, marks, missed, paper_units)
    weak_ids = {t["id"]: t["weak_reasons"] for t in weak}
    for t in topics:
        t["weak_reasons"] = weak_ids.get(t["id"], [])

    unit_views = []
    for u in units:
        unit_topics = [t for t in topics if t["unit_id"] == u["id"]]
        if unit_topics:
            levels = [t["mastery"] for t in unit_topics]
            unit_views.append({"id": u["id"], "name": u["name"], "mastery_pct": logic.mastery_pct(levels),
                               "level_counts": logic.level_counts(levels), "topic_count": len(unit_topics),
                               "topics": unit_topics})

    levels = [t["mastery"] for t in topics]
    ai_levels = [t["mastery"] for t in topics if t["ai_key"]]
    studied_dates = [t["last_reviewed"] for t in topics if t["last_reviewed"]] + [a["at"] for a in activity] + [s["studied_on"] for s in sessions]
    last_studied = max(studied_dates, default=None)
    this_week = logic.week_start(now)

    week_counts = logic.weekly_totals(
        [(date.fromisoformat(a["at"]), 1) for a in activity] + [(date.fromisoformat(d), 1) for d in review_days], now, ACTIVITY_WEEKS)
    week_minutes = logic.weekly_totals([(date.fromisoformat(s["studied_on"]), s["minutes"]) for s in sessions], now, ACTIVITY_WEEKS)
    week_starts = [(this_week - timedelta(weeks=i)).isoformat() for i in range(ACTIVITY_WEEKS - 1, -1, -1)]

    recent = [dict(a) for a in activity] + [
        {"kind": "study", "topic_name": s["topic_name"], "minutes": s["minutes"], "at": s["studied_on"]} for s in sessions]
    recent.sort(key=lambda r: r["at"], reverse=True)

    needs = [r["from_id"] for r in relations if r["to_id"] == subject_id and r["kind"] in ("prereq", "supports")]
    unlocks = [r["to_id"] for r in relations if r["from_id"] == subject_id and r["kind"] in ("prereq", "supports")]

    def neighbour(sid):
        s, m = subjects[sid], mastery_all.get(sid)
        pct = round(100 * m["mastery_sum"] / (logic.MAX_MASTERY * m["topic_count"])) if m else 0
        return {"id": sid, "short_name": s["short_name"], "kind": s["kind"], "lane_id": s["lane_id"],
                "state": states[sid], "mastery_pct": pct}

    subject = {**subjects[subject_id], "state": states[subject_id], "lane_name": lanes[subjects[subject_id]["lane_id"]]["name"]}
    return {
        "today": now.isoformat(),
        "subject": subject,
        "summary": {
            "topic_count": len(topics),
            "started": sum(1 for l in levels if l > 0),
            "mastered": sum(1 for l in levels if l == logic.MAX_MASTERY),
            "mastery_pct": logic.mastery_pct(levels),
            "level": logic.subject_level(logic.mastery_pct(levels))[0],
            "next_level_at": logic.subject_level(logic.mastery_pct(levels))[1],
            "level_counts": logic.level_counts(levels),
            "due_count": sum(1 for t in topics if t["is_due"]),
            "ai_key_count": len(ai_levels),
            "ai_key_pct": logic.mastery_pct(ai_levels),
            "last_studied": last_studied,
            "days_since_studied": (now - date.fromisoformat(last_studied)).days if last_studied else None,
            "minutes_this_week": week_minutes[-1],
            "minutes_total": sum(minutes.values()),
            "card_count": sum(len(c) for c in cards.values()),
            "next_exam": nxt,
            "practice_total": len(practice),
            "practice_done": sum(1 for e in practice if e["done"]),
            "finals_total": sum(1 for e in practice if e["end_of_subject"]),
            "finals_done": sum(1 for e in practice if e["end_of_subject"] and e["done"]),
        },
        "mastery_labels": logic.MASTERY_LABELS,
        "review_after_days": logic.REVIEW_AFTER_DAYS,
        "exam_prep_days": logic.EXAM_PREP_DAYS,
        "units": unit_views,
        "review_queue": logic.review_queue(topics, exam_scope),
        "upcoming_reviews": sorted((t for t in topics if t["next_review"] and not t["is_due"]),
                                   key=lambda t: t["days_until_review"])[:3],
        "exams": exams,
        "practice_exams": practice,
        "weak_spots": weak[:8],
        "activity": {
            "weeks": [{"week_start": s, "count": c, "minutes": m} for s, c, m in zip(week_starts, week_counts, week_minutes)],
            "recent": recent[:8],
        },
        "needs": [neighbour(i) for i in needs],
        "unlocks": [neighbour(i) for i in unlocks],
        "all_subjects": [
            {"id": s["id"], "short_name": s["short_name"], "lane_id": s["lane_id"], "kind": s["kind"]}
            for s in sorted(subjects.values(), key=lambda s: (lanes[s["lane_id"]]["sort_order"], s["tier"], s["grid_row"]))
        ],
        "lanes": list(lanes.values()),
    }


def build_overview(conn, now: date) -> dict:
    """Across all subjects: upcoming exams, weak spots and study time, for the skill tree page."""
    subjects = {s["id"]: s for s in db.fetch_subjects(conn)}
    exams = [exam_view(conn, e, now) for e in study_store.fetch_exams(conn)]
    upcoming = [{**e, "subject_name": subjects[e["subject_id"]]["short_name"]} for e in exams if not e["past"]][:5]

    topics = []
    for t in study_store.started_topics(conn):
        last = date.fromisoformat(t["last_reviewed"]) if t["last_reviewed"] else None
        due = logic.next_review(t["mastery"], last)
        topics.append({**t, "is_due": bool(due and due <= now), "days_until_review": (due - now).days if due else None})
    marks = study_store.mark_downs(conn, (now - MARK_DOWN_WINDOW).isoformat())
    missed = study_store.missed_cards(conn, (now - MISSED_CARD_WINDOW).isoformat())

    week = logic.week_start(now).isoformat()
    minutes_week = sum(s["minutes"] for s in study_store.fetch_sessions(conn, None, week))
    practice = study_store.practice_totals(conn)
    return {
        "today": now.isoformat(),
        "practice_done": practice["done"],
        "practice_total": practice["total"],
        "minutes_this_week": minutes_week,
        "due_total": sum(1 for t in topics if t["is_due"]),
        "upcoming_exams": upcoming,
        "weak_spots": [
            {k: t[k] for k in ("id", "name", "subject_id", "subject_name", "weak_reasons", "weak_score")}
            for t in _weak_list(topics, marks, missed, study_store.weak_paper_units(conn, (now - MARK_DOWN_WINDOW).isoformat()))[:6]
        ],
    }
