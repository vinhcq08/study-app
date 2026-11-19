"""Builds the Today page: a short study plan picked from what's due, your exams and your practice exams."""

from collections import defaultdict
from datetime import date, timedelta

from . import dashboard, db, logic, study_store


def _due_info(t: dict, now: date) -> dict:
    last = date.fromisoformat(t["last_reviewed"]) if t["last_reviewed"] else None
    due = logic.next_review(t["mastery"], last)
    return {**t, "is_due": bool(due and due <= now), "days_until_review": (due - now).days if due else None}


def _item(key, kind, title, detail, minutes, subject, topic=None, url=None, solutions_url=None):
    return {
        "key": key, "kind": kind, "title": title, "detail": detail, "minutes": minutes,
        "subject_id": subject["id"], "subject_name": subject["short_name"],
        "topic_id": topic["id"] if topic else None, "topic_name": topic["name"] if topic else None,
        "url": url, "solutions_url": solutions_url,
    }


def build_plan(conn, now: date) -> list[dict]:
    subjects = {s["id"]: s for s in db.fetch_subjects(conn)}
    states = logic.compute_states(subjects, db.fetch_relations(conn))
    topics = [_due_info(t, now) for t in study_store.all_topics(conn)]
    by_subject = defaultdict(list)
    for t in topics:
        by_subject[t["subject_id"]].append(t)
    items: list[dict] = []
    used_topics: set[str] = set()

    # 1. Overdue reviews, one item per subject, most overdue subject first.
    due = sorted((t for t in topics if t["is_due"]), key=lambda t: t["days_until_review"])
    due_by_subject = defaultdict(list)
    for t in due:
        due_by_subject[t["subject_id"]].append(t)
    for sid, ts in list(due_by_subject.items())[:2]:
        n = len(ts)
        items.append(_item(
            f"review:{sid}", "review", f"Review {n} overdue topic{'s' if n != 1 else ''}",
            ", ".join(t["name"] for t in ts[:4]) + (f" and {n - 4} more" if n > 4 else ""),
            min(25, max(10, logic.REVIEW_MINUTES_PER_TOPIC * n)), subjects[sid], ts[0]))
        used_topics.update(t["id"] for t in ts)

    # 2. Exam prep: the weakest topic covered by your next exam.
    exams = [dashboard.exam_view(conn, e, now) for e in study_store.fetch_exams(conn)]
    upcoming = sorted((e for e in exams if not e["past"]), key=lambda e: e["exam_date"])
    next_exam = upcoming[0] if upcoming else None
    if next_exam and next_exam["days_left"] <= logic.EXAM_PREP_DAYS:
        scope = [t for t in by_subject[next_exam["subject_id"]]
                 if t["unit_id"] in next_exam["unit_ids"] and t["id"] not in used_topics
                 and t["mastery"] < logic.EXAM_PREP_BELOW]
        if scope:
            t = min(scope, key=lambda t: (t["mastery"], t["unit_pos"], t["position"]))
            when = "today" if next_exam["days_left"] == 0 else f"in {next_exam['days_left']} days"
            items.append(_item(
                f"prep:{next_exam['id']}:{t['id']}", "exam_prep", f"Exam prep: {t['name']}",
                f"{next_exam['name']} {when} · {t['unit_name']} · {logic.MASTERY_LABELS[t['mastery']]}",
                25, subjects[next_exam["subject_id"]], t))
            used_topics.add(t["id"])

    # 3. A practice exam for the subject with the next exam, else the first subject in progress.
    in_progress = sorted((s for s in subjects.values() if s["status"] == "in_progress"),
                         key=lambda s: (s["tier"], s["grid_row"]))
    focus = subjects[next_exam["subject_id"]] if next_exam else (in_progress[0] if in_progress else None)
    if focus:
        open_exams = [e for e in study_store.fetch_practice_exams(conn, focus["id"]) if not e["done_on"]]
        final_week = next_exam is not None and next_exam["days_left"] <= logic.FINAL_EXAM_DAYS
        finals = [e for e in open_exams if e["kind"] == "final"]
        others = [e for e in open_exams if e["kind"] != "final"]
        pick = (finals or others) if final_week else (others or finals)
        if pick:
            e = pick[0]
            items.append(_item(
                f"practice:{e['id']}", "practice", f"Practice exam: {e['title']}",
                f"{e['school']} · {e['course']}", 50, focus, url=e["url"], solutions_url=e["solutions_url"]))

    # 4. Flashcards you don't know well yet, for the subject with the most of them.
    weak_cards = study_store.weak_card_counts(conn)
    if weak_cards:
        sid, n = max(weak_cards.items(), key=lambda kv: kv[1])
        items.append(_item(f"cards:{sid}", "cards", f"Practise {n} flashcard{'s' if n != 1 else ''}",
                           "Weakest and least recently practised first", max(5, -(-n // 3)), subjects[sid]))

    # 5. The topic that most needs attention, if it isn't already in the plan.
    overview = dashboard.build_overview(conn, now)
    for w in overview["weak_spots"]:
        if w["id"] not in used_topics:
            t = next(t for t in topics if t["id"] == w["id"])
            items.append(_item(f"attention:{t['id']}", "attention", f"Needs attention: {t['name']}",
                               ", ".join(w["weak_reasons"]).capitalize(), 15, subjects[t["subject_id"]], t))
            used_topics.add(t["id"])
            break

    # 6. Keep a short plan useful: start the next new topic in subjects you're taking, or can start.
    if len(items) < logic.PLAN_MIN_ITEMS:
        ready = sorted((s for s in subjects.values()
                        if s["kind"] == "course" and states[s["id"]] == "ready" and s["status"] == "not_started"),
                       key=lambda s: (s["tier"], s["grid_row"]))
        for s in in_progress + ready:
            if len(items) >= logic.PLAN_MIN_ITEMS:
                break
            fresh = [t for t in by_subject[s["id"]] if t["mastery"] == 0 and t["id"] not in used_topics]
            if fresh:
                t = fresh[0]
                verb = "Continue" if s["status"] == "in_progress" else "Start"
                items.append(_item(f"new:{t['id']}", "new", f"{verb} {s['short_name']}: {t['name']}",
                                   t["unit_name"], 25, s, t))
                used_topics.add(t["id"])
    return items


def build_today(conn, now: date) -> dict:
    today = now.isoformat()
    ticks = study_store.plan_ticks(conn, today)
    plan = build_plan(conn, now)
    for item in plan:
        item["done"] = item["key"] in ticks

    sessions_today = [s for s in study_store.fetch_sessions(conn, None, today) if s["studied_on"] == today]
    week_start = logic.week_start(now)
    week_sessions = study_store.fetch_sessions(conn, None, week_start.isoformat())
    week = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        week.append({"date": d.isoformat(), "minutes": sum(s["minutes"] for s in week_sessions if s["studied_on"] == d.isoformat()),
                     "is_today": d == now, "is_future": d > now})

    days = {date.fromisoformat(d) for d in study_store.study_days(conn) if d}
    subjects = {s["id"]: s for s in db.fetch_subjects(conn)}
    mastery = db.mastery_by_subject(conn)
    taking = []
    for s in sorted(subjects.values(), key=lambda s: (s["tier"], s["grid_row"])):
        if s["status"] != "in_progress":
            continue
        m = mastery.get(s["id"])
        pct = round(100 * m["mastery_sum"] / (logic.MAX_MASTERY * m["topic_count"])) if m else 0
        level, next_at = logic.subject_level(pct)
        taking.append({"id": s["id"], "short_name": s["short_name"], "lane_id": s["lane_id"],
                       "mastery_pct": pct, "level": level, "next_level_at": next_at})

    overview = dashboard.build_overview(conn, now)
    open_items = [i for i in plan if not i["done"]]
    return {
        "today": today,
        "plan": plan,
        "planned_minutes": sum(i["minutes"] for i in open_items),
        "studied_today_minutes": sum(s["minutes"] for s in sessions_today),
        "sessions_today": [{"topic_name": s["topic_name"], "minutes": s["minutes"]} for s in sessions_today],
        "streak_days": logic.streak(days, now),
        "studied_today": now in days,
        "week": week,
        "subjects": taking,
        "upcoming_exams": overview["upcoming_exams"],
        "weak_spots": overview["weak_spots"],
        "practice_done": overview["practice_done"],
        "practice_total": overview["practice_total"],
    }
