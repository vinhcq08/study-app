# Study App

A personal study app built alongside a Bachelor of IT, aimed at graduate study in AI and Computer Science.

Four pages in a "colour editorial" style: each page reads like a daily paper printed in colour, with serif headlines (Newsreader), a five-ink palette (cobalt, tomato, teal, plum, sunflower), and the lead item on a block of colour. There is a light and a dark version; switch with the Auto / Light / Dark button in the menu (Auto follows your device). Colours are tokens at the top of `static/css/app.css`; the editorial treatments are in `static/css/editorial.css`.

- **Today** (home page): a short plan picked once each day: a review session for subjects with topics due, exam prep in the week before an exam, a past paper, due flashcards, the topic that most needs attention, and new topics when there's little else. Ticking an item does the real thing (marks the topics studied, ticks the past paper off), and doing the thing elsewhere ticks the item. Set **Time today** and the plan fits it, in priority order; add more when you finish early. Also your streak, this week's study time, exam countdowns and subject levels (1 to 5, from topic mastery).
- **Skill tree**: all 43 degree subjects plus 7 MIT gap-fillers, arranged by prerequisite. Select a subject to see its level and what to do next. The comparison with MIT Course 6-3 is folded away under the tree.
- **Subjects**: what you're taking now (level, mastery, topics due, next exam, past papers), then what's ready to start, what's done, and the rest by area. Two more tabs:
  - **Semester plan**: put each subject in a semester. You're warned when a prerequisite is planned for the same or a later semester, or not at all.
  - **Grades**: your GPA overall and by area, on the common 4.0 scale (A 4.0, A− 3.7, B+ 3.3 …; your university's may differ). Numeric marks are averaged separately. Every subject counts equally because credits aren't recorded.

  Also where you download and restore a backup.
- **Subject dashboard** (one per subject): set its status, semester and grade at the top, then:
  - **Topics**: 710 topics grouped into units, each with a five-level mastery scale, notes, flashcards, resources and links to related topics in other subjects.
  - **Review session**: spaced repetition. Topics come due 2 to 30 days after you study them; "Start review" steps through the due ones and you rate each from 1 to 4.
  - **Your exam dates**: a countdown and a readiness score (average mastery of the units the exam covers). In the 21 days before an exam, its weaker topics come up in Today's plan.
  - **Past papers**: 131 exams that MIT, Berkeley, Stanford, CMU and others publish openly, mapped to the units they cover. Tick each one off when done, then note your score, the time it took and the units that went badly. Finals are marked as end-of-subject exams.
  - **Flashcards**: practise with Again / Hard / Good / Easy. Each card has its own due date (Leitner boxes: 1, 3, 7, 21 days), and the topic's mastery follows its cards.
  - **Needs attention**: topics you're struggling with: marked down, flashcards you keep missing, or in a unit that went badly on a past paper (until you reach Confident).

**Study timer and focus mode**: starting a session (15, 25 or 50 minutes) opens a calm, full-screen focus view. Leave it and the timer keeps running in a small bar on every page. When it ends, the minutes are logged and one question asks how well you know the topic now, which sets its mastery.

**Backup**: everything you record is in one SQLite database (or, online, in your browser). Subjects → Your data → Download backup saves it as a JSON file; Restore from backup puts it back, on any device. A bad file changes nothing.

On phones the menu moves to a tab bar along the bottom.

## Run it

You need Python 3.11 or newer.

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

On Windows, use `.venv\Scripts\activate` instead.

```bash
pip install -r requirements.txt
```

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000. Your progress is stored in `study.db`, which is created on first start.

Run the tests:

```bash
pytest
```

## Use it online (GitHub Pages)

Every push to `main` publishes the app to **https://vinhcq08.github.io/study-app/** through the "Publish to GitHub Pages" workflow. That version needs no server: the same Python code runs inside your browser with [Pyodide](https://pyodide.org), and your progress is saved in that browser (IndexedDB) on that device. It doesn't sync between devices, and clearing the site's data in your browser erases it, so download a backup now and then (Subjects → Your data). Python starts once when you open the site; the pages then switch instantly, because the site's front page keeps Python running and shows each page in a frame (the address bar follows along, e.g. `#subject.html?id=linalg`).

To build the same site locally: `python scripts/build_pages.py --pyodide <folder with the Pyodide release files> --out _site`, then serve `_site` with any static file server.

## Run it on GitHub (Codespaces)

On the repository page, choose **Code → Codespaces → Create codespace**. The app installs and starts by itself, and opens in a browser tab. Your progress is kept in that codespace until you delete it. Free GitHub accounts include a monthly allowance of Codespaces hours.

## Host it online

GitHub Pages can't run this app, because it needs its Python server and database. To host it, use any service that runs a Docker image, such as Render, Railway or Fly.io: point it at this repository and it builds the `Dockerfile`. Attach a persistent volume at `/data`, or your progress resets whenever the service restarts. The app has no login, so anyone with the link can see and change your data.

## How it fits together

| Path | What it does |
|---|---|
| `data/practice_exams.json` | Past papers per subject: link, school, course, kind (quiz, midterm, final, practice) and the units each covers. Restart to load changes; your ticks are kept. |
| `data/topic_links.json` | Links between topics in different subjects, with a one-line reason. |
| `data/topics.json` | Units and topics for every subject. A leading `*` marks a topic that is key for AI. Edit it to match your real syllabus, then restart. |
| `data/curriculum.json` | The subjects, their tree position, prerequisites and MIT matches. Edit this to change the curriculum, then restart the server. |
| `app/db.py` | SQLite schema for subjects and topics, loading the curriculum, and saving progress. Reloading never deletes your progress. |
| `app/study_store.py` | Storage for exams, past papers, study sessions, flashcards, resources and topic links. |
| `app/browser.py` | Runs the same API inside the browser for the GitHub Pages version. |
| `scripts/build_pages.py` | Builds the GitHub Pages site (pages + Python code + Pyodide). `scripts/pages_shell.html` becomes its front page: it starts Python once and shows the pages in a frame. |
| `app/today.py` | Builds the Today plan, streak, weekly minutes and subject levels. |
| `app/dashboard.py` | Builds each subject dashboard and the cross-subject overview. |
| `app/services.py` | Topic changes that touch several tables (mastery, review dates, activity log, starting the subject). |
| `app/clock.py` | The app's idea of "today"; tests replace it. |
| `app/logic.py` | The rules: which subjects are ready or locked, what a change unlocks, a cycle check, topic mastery percentages and review scheduling. |
| `app/planning.py` | Grades (GPA by area) and the semester plan with its prerequisite-order warnings. |
| `app/backup.py` | Exports everything you've recorded as JSON, and restores it in one transaction. |
| `app/main.py` | Creates the FastAPI app and serves the web pages. |
| `app/routes/` | The API: `tree.py` (skill tree, progress, overview, semester plan and grades), `subjects.py` (dashboard, exam dates, past papers, review sessions, flashcard practice), `topics.py` (mastery, notes, sessions, flashcards, resources), `today.py` (the Today plan, its ticks, and settings such as the daily time budget), `backup.py` (download and restore). |
| `static/` | The pages (`index.html` is Today, `tree.html`, `subjects.html`, `subject.html`), their CSS (colour and font tokens at the top of `css/app.css`, the editorial look in `css/editorial.css`) and JavaScript: `nav.js` (menu and theme switch), `timer.js` (timer, focus mode and the after-session question), `review.js` (review sessions), `paper-result.js` (past paper results), `planning.js` (semester plan and grades tabs), `practice.js` (flashcard practice), one script per page. No build step. |
| `tests/` | Tests for the data, the rules and the API. |

### Database tables

- `lanes`: subject families (rows in the tree)
- `subjects`: one row per subject or gap-filler
- `relations`: `prereq`, `supports` (gap-filler helps with a subject) and `related` links
- `progress`: your status, semester and grade for each subject
- `units` and `topics`: the syllabus for each subject (topics removed from `topics.json` are retired, not deleted, so your progress is kept)
- `topic_progress`: your mastery level (0 Not started to 4 Mastered), notes and last review date for each topic
- `activity`: one row per change, for the activity chart
- `exams`, `exam_units`: your own exam dates and the units each covers
- `practice_exams`, `practice_exam_units`, `practice_exam_progress`: the past-paper catalog, your ticks, and your score, time and weak units for each
- `study_sessions`: minutes logged by the timer
- `flashcards`, `card_reviews`: cards, their Leitner box and due date, and every answer
- `resources`: links you attach to topics
- `topic_links`: connections between topics in different subjects
- `daily_plans`, `plan_ticks`: each day's Today plan, fixed once made, and the items you ticked off
- `settings`: your preferences (the daily time budget)

### Review scheduling

After you study or review a topic, it comes due again after 2 days (Learning), 4 days (Practising), 10 days (Confident) or 30 days (Mastered). Change `REVIEW_AFTER_DAYS` in `app/logic.py` to tune this.

### Past paper links

The links were found by web search in November 2026 and point to official course sites (MIT OpenCourseWare, Berkeley course pages and the HKN exam archive, Stanford, CMU, UW, Brown, Michigan). Course sites do move, so if a link breaks, update it in `data/practice_exams.json`. The units each exam covers are an estimate from the course's usual order and the exam's topics.

### Adding a subject

Add an entry to `data/curriculum.json` with a free `tier` and `row` cell, list its `prereqs`, and restart. The tests check that every link points to a real subject, that no two subjects share a cell, and that prerequisites have no cycles.
