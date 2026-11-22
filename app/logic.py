"""Skill tree rules, kept free of database and web code so they are easy to test."""

from datetime import date, timedelta

# A subject's state in the tree:
#   done / in_progress  - what you set
#   ready               - every prerequisite is done
#   locked              - at least one prerequisite isn't done yet
DONE, IN_PROGRESS, READY, LOCKED = "done", "in_progress", "ready", "locked"


def required_prereqs(subject_id: str, subjects: dict, relations: list[dict]) -> list[str]:
    """Prerequisites that block this subject.

    Gap-fillers are optional self-study, so they never block one of your degree courses.
    """
    is_course = subjects[subject_id]["kind"] == "course"
    return [
        r["from_id"]
        for r in relations
        if r["kind"] == "prereq"
        and r["to_id"] == subject_id
        and not (is_course and subjects[r["from_id"]]["kind"] == "gap_filler")
    ]


def compute_states(subjects: dict, relations: list[dict]) -> dict[str, str]:
    """Map every subject id to done, in_progress, ready or locked."""
    states = {}
    for sid, s in subjects.items():
        if s["status"] == "done":
            states[sid] = DONE
        elif s["status"] == "in_progress":
            states[sid] = IN_PROGRESS
        else:
            prereqs = required_prereqs(sid, subjects, relations)
            all_done = all(subjects[p]["status"] == "done" for p in prereqs)
            states[sid] = READY if all_done else LOCKED
    return states


def newly_unlocked(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Subjects that were locked and are now ready."""
    return [sid for sid, state in after.items() if before.get(sid) == LOCKED and state == READY]


def find_cycle(relations: list[dict]) -> list[str] | None:
    """Return one prerequisite cycle if the curriculum has any, otherwise None."""
    graph: dict[str, list[str]] = {}
    for r in relations:
        if r["kind"] == "prereq":
            graph.setdefault(r["from_id"], []).append(r["to_id"])

    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GREY
        stack.append(node)
        for nxt in graph.get(node, []):
            if color.get(nxt, WHITE) == GREY:
                return stack[stack.index(nxt):] + [nxt]
            if color.get(nxt, WHITE) == WHITE:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in list(graph):
        if color.get(node, WHITE) == WHITE:
            found = visit(node)
            if found:
                return found
    return None


# ---- Topic mastery and review scheduling ----

MASTERY_LABELS = ["Not started", "Learning", "Practising", "Confident", "Mastered"]
MAX_MASTERY = len(MASTERY_LABELS) - 1

# Days after your last review before a topic comes due again.
# Spaced repetition: the better you know a topic, the longer you can wait.
REVIEW_AFTER_DAYS = {1: 2, 2: 4, 3: 10, 4: 30}


def mastery_pct(levels: list[int]) -> int:
    """Average mastery as a percentage (every topic Mastered = 100)."""
    if not levels:
        return 0
    return round(100 * sum(levels) / (MAX_MASTERY * len(levels)))


def next_review(mastery: int, last_reviewed: date | None) -> date | None:
    if mastery == 0 or last_reviewed is None:
        return None
    return last_reviewed + timedelta(days=REVIEW_AFTER_DAYS[mastery])


def level_counts(levels: list[int]) -> list[int]:
    """How many topics sit at each mastery level, from Not started to Mastered."""
    counts = [0] * (MAX_MASTERY + 1)
    for level in levels:
        counts[level] += 1
    return counts


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday


def weekly_counts(days: list[date], today: date, weeks: int = 12) -> list[dict]:
    """Number of study actions in each of the last `weeks` weeks, oldest first."""
    this_week = week_start(today)
    starts = [this_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    counts = {s: 0 for s in starts}
    for d in days:
        s = week_start(d)
        if s in counts:
            counts[s] += 1
    return [{"week_start": s.isoformat(), "count": counts[s]} for s in starts]


# ---- Flashcards (Leitner boxes) ----

CARD_RESULTS = ("again", "hard", "good", "easy")
MAX_BOX = 4


def next_box(box: int, result: str) -> int:
    """Move a card between boxes. Box 0 is a new card, box 4 is one you know well."""
    if result == "again":
        return 1
    if result == "hard":
        return max(1, box)
    if result == "good":
        return min(MAX_BOX, box + 1)
    if result == "easy":
        return min(MAX_BOX, box + 2)
    raise ValueError(f"unknown result {result!r}")


# Days until a card comes back, by the box it's now in.
CARD_REVIEW_DAYS = {1: 1, 2: 3, 3: 7, 4: 21}


def next_card_due(box: int, on: date) -> date:
    return on + timedelta(days=CARD_REVIEW_DAYS.get(box, 1))


def mastery_from_cards(boxes: list[int]) -> int | None:
    """A topic's mastery from its flashcards: the average box. None if it has no cards."""
    if not boxes:
        return None
    return max(0, min(MAX_MASTERY, round(sum(boxes) / len(boxes))))


# ---- Exams ----

EXAM_PREP_DAYS = 21   # how far ahead an exam starts shaping the review queue
EXAM_PREP_BELOW = 3   # topics below Confident count as exam prep


def next_exam(exams: list[dict], today: date) -> dict | None:
    upcoming = [e for e in exams if date.fromisoformat(e["exam_date"]) >= today]
    return min(upcoming, key=lambda e: e["exam_date"]) if upcoming else None


def review_queue(topics: list[dict], exam_topic_ids: set[str]) -> list[dict]:
    """Order the review queue.

    1. Due topics that are on the next exam, most overdue first.
    2. Other due topics, most overdue first.
    3. Exam prep: topics on the next exam that aren't due but are below Confident, weakest first.
    """
    due = [t for t in topics if t["is_due"]]
    on_exam = sorted((t for t in due if t["id"] in exam_topic_ids), key=lambda t: t["days_until_review"])
    others = sorted((t for t in due if t["id"] not in exam_topic_ids), key=lambda t: t["days_until_review"])
    prep = sorted(
        (t for t in topics if t["id"] in exam_topic_ids and not t["is_due"] and t["mastery"] < EXAM_PREP_BELOW),
        key=lambda t: (t["mastery"], t["name"]),
    )
    return (
        [{**t, "reason": "due", "for_exam": True} for t in on_exam]
        + [{**t, "reason": "due", "for_exam": False} for t in others]
        + [{**t, "reason": "exam_prep", "for_exam": True} for t in prep]
    )


# ---- Weak spots ----

# "Needs attention" means you're struggling with a topic, not that it's late:
# lateness already shows as "due for review".
WEAK_THRESHOLD = 3        # minimum score to be listed


def weak_spot(mark_downs: int, missed_cards: int, struggled_on_paper: bool = False) -> tuple[int, list[str]]:
    """Score how much a topic needs attention, with the reasons in plain words."""
    score, reasons = 0, []
    if struggled_on_paper:
        score += 3
        reasons.append("went badly on a past paper")
    if mark_downs:
        score += 4 * mark_downs
        reasons.append("marked down once" if mark_downs == 1 else f"marked down {mark_downs} times")
    if missed_cards:
        score += 2 * missed_cards
        reasons.append("missed 1 flashcard" if missed_cards == 1 else f"missed {missed_cards} flashcards")
    return score, reasons


def weekly_totals(items: list[tuple[date, int]], today: date, weeks: int = 12) -> list[int]:
    """Sum values into the last `weeks` weeks (Monday starts), oldest first."""
    this_week = week_start(today)
    starts = [this_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    totals = {s: 0 for s in starts}
    for d, value in items:
        s = week_start(d)
        if s in totals:
            totals[s] += value
    return [totals[s] for s in starts]


# ---- Levels and streaks ----

LEVEL_STEP = 20  # each level is 20 percentage points of topic mastery


def subject_level(mastery_pct: int) -> tuple[int, int | None]:
    """Level 1 to 5 from a subject's mastery %, and the % where the next level starts."""
    level = min(5, mastery_pct // LEVEL_STEP + 1)
    return level, (None if level == 5 else level * LEVEL_STEP)


def streak(study_days: set[date], today: date) -> int:
    """Days in a row with any study. A streak survives until the end of the day after the last study day."""
    day = today if today in study_days else today - timedelta(days=1)
    count = 0
    while day in study_days:
        count += 1
        day -= timedelta(days=1)
    return count


# ---- Today's plan ----

REVIEW_MINUTES_PER_TOPIC = 5
PLAN_MIN_ITEMS = 3
FINAL_EXAM_DAYS = 7   # in the last week before an exam, suggest the end-of-subject practice exam
