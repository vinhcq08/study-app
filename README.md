# Study App

A personal study app built alongside a Bachelor of IT, aimed at graduate study in AI and Computer Science.

Three pages, with a light "engineering notebook" theme and a dark "night lab" theme (switch with the Auto / Light / Dark button in the menu; Auto follows your device):

- **Today** (home page): a short study plan picked for you each day: overdue reviews, exam prep for your next exam, a practice exam, flashcards, the topic that most needs attention, and new topics when there's little else. Tick items off, start a timed session from any item, and see your daily streak, this week's study time, your exam countdowns and your subjects' levels (1 to 5, from topic mastery).
- **Skill tree**: all 43 degree subjects plus 7 MIT gap-fillers, arranged by prerequisite and matched against MIT Course 6-3. Select a subject to see its level and what to do next, mark it in progress or done, and record semester and grade.
- **Subject dashboard** (one per subject):
  - **Topics**: 710 topics grouped into units, each with a five-level mastery scale, notes, flashcards, resources and links to related topics in other subjects.
  - **Review queue**: spaced repetition. Topics come due 2 to 30 days after you study them, and in the 21 days before one of your exams its weaker topics join the queue as exam prep.
  - **Practice exams**: 131 past exams that MIT, Berkeley, Stanford, CMU and others publish openly, mapped to the units they cover. Tick each one off when done. Finals are marked as end-of-subject exams.
  - **Your exam dates**: a countdown and a readiness score (average mastery of the units the exam covers).
  - **Flashcards**: practise with Again / Hard / Good / Easy. Cards move between Leitner boxes, and the topic's mastery follows its cards. Full screen on phones.
  - **Needs attention**: topics that are long overdue, that you've marked down, or whose flashcards you keep missing.

**Study timer and focus mode**: starting a session (15, 25 or 50 minutes) opens a calm, full-screen focus view. Leave it and the timer keeps running in a small bar on every page; when it ends, the minutes are logged to the topic.

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

Every push to `main` publishes the app to **https://vinhcq08.github.io/study-app/** through the "Publish to GitHub Pages" workflow. That version needs no server: the same Python code runs inside your browser with [Pyodide](https://pyodide.org), and your progress is saved in that browser (IndexedDB) on that device. It doesn't sync between devices, and clearing the site's data in your browser erases it.

To build the same site locally: `python scripts/build_pages.py --pyodide <folder with the Pyodide release files> --out _site`, then serve `_site` with any static file server.

## Run it on GitHub (Codespaces)

On the repository page, choose **Code → Codespaces → Create codespace**. The app installs and starts by itself, and opens in a browser tab. Your progress is kept in that codespace until you delete it. Free GitHub accounts include a monthly allowance of Codespaces hours.

## Host it online

GitHub Pages can't run this app, because it needs its Python server and database. To host it, use any service that runs a Docker image, such as Render, Railway or Fly.io: point it at this repository and it builds the `Dockerfile`. Attach a persistent volume at `/data`, or your progress resets whenever the service restarts. The app has no login, so anyone with the link can see and change your data.

## How it fits together

| Path | What it does |
|---|---|
| `data/practice_exams.json` | Practice exams per subject: link, school, course, kind (quiz, midterm, final, practice) and the units each covers. Restart to load changes; your ticks are kept. |
| `data/topic_links.json` | Links between topics in different subjects, with a one-line reason. |
| `data/topics.json` | Units and topics for every subject. A leading `*` marks a topic that is key for AI. Edit it to match your real syllabus, then restart. |
| `data/curriculum.json` | The subjects, their tree position, prerequisites and MIT matches. Edit this to change the curriculum, then restart the server. |
| `app/db.py` | SQLite schema for subjects and topics, loading the curriculum, and saving progress. Reloading never deletes your progress. |
| `app/study_store.py` | Storage for exams, practice exams, study sessions, flashcards, resources and topic links. |
| `app/browser.py` | Runs the same API inside the browser for the GitHub Pages version. |
| `scripts/build_pages.py` | Builds the GitHub Pages site (pages + Python code + Pyodide). |
| `app/today.py` | Builds the Today plan, streak, weekly minutes and subject levels. |
| `app/dashboard.py` | Builds each subject dashboard and the cross-subject overview. |
| `app/services.py` | Topic changes that touch several tables (mastery, review dates, activity log, starting the subject). |
| `app/clock.py` | The app's idea of "today"; tests replace it. |
| `app/logic.py` | The rules: which subjects are ready or locked, what a change unlocks, a cycle check, topic mastery percentages and review scheduling. |
| `app/main.py` | Creates the FastAPI app and serves the web pages. |
| `app/routes/` | The API: `tree.py` (skill tree, progress, overview), `subjects.py` (dashboard, exam dates, practice exams, flashcard practice), `topics.py` (mastery, notes, sessions, flashcards, resources), `today.py` (the Today plan and its ticks). |
| `static/` | The pages (`index.html` is Today, `tree.html`, `subject.html`), their CSS (theme colours live at the top of `css/app.css`) and JavaScript: `nav.js` (menu and theme switch), `timer.js` (timer and focus mode), `practice.js` (flashcard practice), one script per page. No build step. |
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
- `practice_exams`, `practice_exam_units`, `practice_exam_progress`: the practice-exam catalog and your ticks
- `study_sessions`: minutes logged by the timer
- `flashcards`, `card_reviews`: cards, their Leitner box, and every answer
- `resources`: links you attach to topics
- `topic_links`: connections between topics in different subjects
- `plan_ticks`: Today items you ticked off, per day

### Review scheduling

After you study or review a topic, it comes due again after 2 days (Learning), 4 days (Practising), 10 days (Confident) or 30 days (Mastered). Change `REVIEW_AFTER_DAYS` in `app/logic.py` to tune this.

### Practice exam links

The links were found by web search in November 2026 and point to official course sites (MIT OpenCourseWare, Berkeley course pages and the HKN exam archive, Stanford, CMU, UW, Brown, Michigan). Course sites do move, so if a link breaks, update it in `data/practice_exams.json`. The units each exam covers are an estimate from the course's usual order and the exam's topics.

### Adding a subject

Add an entry to `data/curriculum.json` with a free `tier` and `row` cell, list its `prereqs`, and restart. The tests check that every link points to a real subject, that no two subjects share a cell, and that prerequisites have no cycles.
