"""Builds the Today page: a short study plan picked from what's due, your exams and your past papers.

The plan is built once per day and saved, so it doesn't reshuffle while you work. An item
counts as done when its real action happens (you review the topics, study the topic, tick
off the past paper, practise the cards), or when you tick it, which does that action for you.
"""

from collections import defaultdict
from datetime import date, timedelta

from . import dashboard, db, logic, services, study_store

TOPIC_KINDS = {"exam_prep", "attention", "new"}


def _due_info(t: dict, now: date) -> dict:
    last = date.fromisoformat(t["last_reviewed"]) if t["last_reviewed"] else None
    due = logic.next_review(t["mastery"], last)
    return {**t, "is_due": bool(due and due <= now), "days_until_review": (due - now).days if due else None}


def _item(key, kind, title, detail, minutes, subject, topic=None, **extra):
    return {
        "key": key, "kind": kind, "title": title, "detail": detail, "minutes": minutes,
        "subject_id": subject["id"], "subject_name": subject["short_name"],
        "topic_id": topic["id"] if topic else None, "topic_name": topic["name"] if topic else None,
        "url": None, "solutions_url": None, **extra,
    }


def build_plan(conn, now: date, exclude_keys=frozenset(), exclude_topics=frozenset(), limit=None) -> list[dict]:
    """Pick plan items. Items whose key or topic is excluded are skipped (used to add more later)."""
    today = now.isoformat()
    subjects = {s["id"]: s for s in db.fetch_subjects(conn)}
    states = logic.compute_states(subjects, db.fetch_relations(conn))
    topics = [_due_info(t, now) for t in study_store.all_topics(conn)]
    by_subject = defaultdict(list)
    for t in topics:
        by_subject[t["subject_id"]].append(t)
    items: list[dict] = []
    # Topics already studied today or already in the plan aren't suggested again.
    used = set(exclude_topics) | {t["id"] for t in topics if t["last_reviewed"] == today}

    def add(item):
        if item["key"] not in exclude_keys:
            items.append(item)

    # 1. Overdue reviews, one item per subject, most overdue subject first.
    due = sorted((t for t in topics if t["is_due"]), key=lambda t: t["days_until_review"])
    due_by_subject = defaultdict(list)
    for t in due:
        due_by_subject[t["subject_id"]].append(t)
    for sid, ts in list(due_by_subject.items())[:2]:
        n = len(ts)
        add(_item(f"review:{sid}", "review", f"Review {n} overdue topic{'s' if n != 1 else ''}",
                  ", ".join(t["name"] for t in ts[:4]) + (f" and {n - 4} more" if n > 4 else ""),
                  min(25, max(10, logic.REVIEW_MINUTES_PER_TOPIC * n)), subjects[sid], ts[0], count=n))
        used.update(t["id"] for t in ts)

    # 2. Exam prep: the weakest topics covered by your next exam (two in its last week).
    exams = [dashboard.exam_view(conn, e, now) for e in study_store.fetch_exams(conn)]
    upcoming = sorted((e for e in exams if not e["past"]), key=lambda e: e["exam_date"])
    next_exam = upcoming[0] if upcoming else None
    if next_exam and next_exam["days_left"] <= logic.EXAM_PREP_DAYS:
        scope = sorted((t for t in by_subject[next_exam["subject_id"]]
                        if t["unit_id"] in next_exam["unit_ids"] and t["id"] not in used
                        and t["mastery"] < logic.EXAM_PREP_BELOW),
                       key=lambda t: (t["mastery"], t["unit_pos"], t["position"]))
        when = "today" if next_exam["days_left"] == 0 else f"in {next_exam['days_left']} days"
        for t in scope[:2 if next_exam["days_left"] <= logic.FINAL_EXAM_DAYS else 1]:
            add(_item(f"prep:{next_exam['id']}:{t['id']}", "exam_prep", f"Exam prep: {t['name']}",
                      f"{next_exam['name']} {when} · {t['unit_name']} · {logic.MASTERY_LABELS[t['mastery']]}",
                      25, subjects[next_exam["subject_id"]], t))
            used.add(t["id"])

    # 3. A past paper for the subject with the next exam, else the first subject in progress.
    in_progress = sorted((s for s in subjects.values() if s["status"] == "in_progress"),
                         key=lambda s: (s["tier"], s["grid_row"]))
    focus = subjects[next_exam["subject_id"]] if next_exam else (in_progress[0] if in_progress else None)
    if focus:
        open_exams = [e for e in study_store.fetch_practice_exams(conn, focus["id"])
                      if not e["done_on"] and f"practice:{e['id']}" not in exclude_keys]
        final_week = next_exam is not None and next_exam["days_left"] <= logic.FINAL_EXAM_DAYS
        finals = [e for e in open_exams if e["kind"] == "final"]
        others = [e for e in open_exams if e["kind"] != "final"]
        pick = (finals or others) if final_week else (others or finals)
        if pick:
            e = pick[0]
            add(_item(f"practice:{e['id']}", "practice", f"Past paper: {e['title']}",
                      f"{e['school']} · {e['course']}", 50, focus,
                      exam_id=e["id"], url=e["url"], solutions_url=e["solutions_url"]))

    # 4. Flashcards that are due, for the subject with the most of them.
    due_cards = study_store.due_card_counts(conn, today)
    if due_cards:
        sid, n = max(due_cards.items(), key=lambda kv: kv[1])
        add(_item(f"cards:{sid}", "cards", f"Practise {n} due flashcard{'s' if n != 1 else ''}",
                  "Weakest first", max(5, -(-n // 3)), subjects[sid], count=n))

    # 5. The topic you're struggling with most, if it isn't already in the plan.
    for w in dashboard.build_overview(conn, now)["weak_spots"]:
        if w["id"] not in used:
            t = next(t for t in topics if t["id"] == w["id"])
            add(_item(f"attention:{t['id']}", "attention", f"Needs attention: {t['name']}",
                      ", ".join(w["weak_reasons"]).capitalize(), 15, subjects[t["subject_id"]], t))
            used.add(t["id"])
            break

    # 6. Keep a short plan useful: the next new topic in subjects you're taking, or can start.
    wanted = limit if limit is not None else logic.PLAN_MIN_ITEMS
    if len(items) < wanted:
        ready = sorted((s for s in subjects.values()
                        if s["kind"] == "course" and states[s["id"]] == "ready" and s["status"] == "not_started"),
                       key=lambda s: (s["tier"], s["grid_row"]))
        for s in in_progress + ready:
            if len(items) >= wanted:
                break
            fresh = [t for t in by_subject[s["id"]] if t["mastery"] == 0 and t["id"] not in used]
            if fresh:
                t = fresh[0]
                verb = "Continue" if s["status"] == "in_progress" else "Start"
                add(_item(f"new:{t['id']}", "new", f"{verb} {s['short_name']}: {t['name']}",
                          t["unit_name"], 25, s, t))
                used.add(t["id"])
    return items[:limit] if limit is not None else items


def evaluate(conn, plan: list[dict], now: date) -> list[dict]:
    """Work out which items are done, from what actually happened today and your ticks."""
    today = now.isoformat()
    ticks = study_store.plan_ticks(conn, today)
    topics = {t["id"]: _due_info(t, now) for t in study_store.all_topics(conn)}
    due_count = defaultdict(int)
    for t in topics.values():
        if t["is_due"]:
            due_count[t["subject_id"]] += 1
    papers_done = study_store.done_practice_exam_ids(conn)
    cards_today = study_store.card_reviews_on(conn, today)
    out = []
    for item in plan:
        kind = item["kind"]
        if kind == "review":
            done = due_count[item["subject_id"]] == 0
        elif kind in TOPIC_KINDS:
            t = topics.get(item["topic_id"])
            done = bool(t and t["last_reviewed"] == today)
        elif kind == "practice":
            done = item["exam_id"] in papers_done
        elif kind == "cards":
            done = cards_today.get(item["subject_id"], 0) >= item.get("count", 1)
        else:
            done = False
        ticked = item["key"] in ticks
        out.append({**item, "done": done or ticked, "done_by": "action" if done else ("tick" if ticked else None)})
    return out


def todays_plan(conn, now: date) -> list[dict]:
    """Today's saved plan, building it first if this is the first visit of the day."""
    today = now.isoformat()
    plan = study_store.get_daily_plan(conn, today)
    if plan is None:
        plan = build_plan(conn, now)
        study_store.save_daily_plan(conn, today, plan)
    return plan


def tick(conn, now: date, key: str, done: bool) -> None:
    """Tick or untick a plan item. Ticking does the item's real action."""
    today = now.isoformat()
    item = next((i for i in todays_plan(conn, now) if i["key"] == key), None)
    if item is None:
        raise KeyError(key)
    kind = item["kind"]
    if done:
        if kind == "review":
            for t in study_store.all_topics(conn):
                if t["subject_id"] == item["subject_id"] and _due_info(t, now)["is_due"]:
                    services.change_topic(conn, db.fetch_topic(conn, t["id"]), today, studied=True)
        elif kind in TOPIC_KINDS and item["topic_id"]:
            services.change_topic(conn, db.fetch_topic(conn, item["topic_id"]), today, studied=True)
        elif kind == "practice":
            study_store.set_practice_done(conn, item["exam_id"], today)
    elif kind == "practice":
        study_store.set_practice_done(conn, item["exam_id"], None)
    study_store.set_plan_tick(conn, today, key, done)


def add_more(conn, now: date, count: int = 3) -> int:
    """Add up to `count` new items to today's plan. Returns how many were added."""
    plan = todays_plan(conn, now)
    extra = build_plan(conn, now, exclude_keys={i["key"] for i in plan},
                       exclude_topics={i["topic_id"] for i in plan if i["topic_id"]}, limit=count)
    study_store.save_daily_plan(conn, now.isoformat(), plan + extra)
    return len(extra)


def rebuild(conn, now: date) -> None:
    """Rebuild today's plan, keeping the items you've already done."""
    done = [i for i in evaluate(conn, todays_plan(conn, now), now) if i["done"]]
    fresh = build_plan(conn, now, exclude_keys={i["key"] for i in done},
                       exclude_topics={i["topic_id"] for i in done if i["topic_id"]})
    keep = [{k: v for k, v in i.items() if k not in ("done", "done_by")} for i in done]
    study_store.save_daily_plan(conn, now.isoformat(), keep + fresh)


def build_today(conn, now: date) -> dict:
    today = now.isoformat()
    plan = evaluate(conn, todays_plan(conn, now), now)

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
