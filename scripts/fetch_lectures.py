"""Collect lecture lists from MIT OpenCourseWare (and a few other open courses) for each subject.

Writes data/lecture_catalog.json: for each course, its lectures with their real titles and links.
scripts/match_lectures.py then links lectures to topics. Run this again only to refresh the catalog;
the app reads data/lectures.json, which is committed.

    python scripts/fetch_lectures.py
"""

import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OCW = "https://ocw.mit.edu"

# course id -> (title shown in the app, OCW slug, where its lectures are listed)
# Sections: "videos:<path>" a video gallery, "notes:<path>" a table of lecture topics,
# "pages:<prefix>" course pages whose links name the lessons (chapters, weeks, units).
COURSES = {
    "18.01": ("MIT 18.01 Single Variable Calculus (Fall 2006)", "18-01-single-variable-calculus-fall-2006", ["videos:video_galleries/video-lectures/"]),
    "18.02": ("MIT 18.02 Multivariable Calculus (Fall 2007)", "18-02-multivariable-calculus-fall-2007", ["videos:video_galleries/video-lectures/"]),
    "18.03": ("MIT 18.03 Differential Equations (Spring 2010)", "18-03-differential-equations-spring-2010", ["videos:video_galleries/video-lectures/"]),
    "18.06": ("MIT 18.06 Linear Algebra (Spring 2010)", "18-06-linear-algebra-spring-2010", ["videos:video_galleries/video-lectures/"]),
    "18.065": ("MIT 18.065 Matrix Methods in Data Analysis, Signal Processing, and Machine Learning (Spring 2018)", "18-065-matrix-methods-in-data-analysis-signal-processing-and-machine-learning-spring-2018", ["videos:video_galleries/video-lectures/"]),
    "18.404": ("MIT 18.404J Theory of Computation (Fall 2020)", "18-404j-theory-of-computation-fall-2020", ["videos:video_galleries/video-lectures/"]),
    "6.042": ("MIT 6.042J Mathematics for Computer Science (Fall 2010)", "6-042j-mathematics-for-computer-science-fall-2010", ["videos:video_galleries/video-lectures/"]),
    "6.041": ("MIT 6.041 Probabilistic Systems Analysis and Applied Probability (Fall 2010)", "6-041-probabilistic-systems-analysis-and-applied-probability-fall-2010", ["videos:video_galleries/video-lectures/"]),
    "6.046": ("MIT 6.046J Design and Analysis of Algorithms (Spring 2015)", "6-046j-design-and-analysis-of-algorithms-spring-2015", ["videos:video_galleries/lecture-videos/"]),
    "6.006": ("MIT 6.006 Introduction to Algorithms (Spring 2020)", "6-006-introduction-to-algorithms-spring-2020", ["videos:video_galleries/lecture-videos/"]),
    "6.034": ("MIT 6.034 Artificial Intelligence (Fall 2010)", "6-034-artificial-intelligence-fall-2010", ["videos:video_galleries/lecture-videos/"]),
    "6.867": ("MIT 6.867 Machine Learning (Fall 2006)", "6-867-machine-learning-fall-2006", ["notes:pages/lecture-notes/"]),
    "6.S191": ("MIT 6.S191 Introduction to Deep Learning (2026)", None, ["dl:https://introtodeeplearning.com/"]),
    "CS50": ("Harvard CS50x Introduction to Computer Science (2026)", None, ["cs50:https://cs50.harvard.edu/x/"]),
    "6.837": ("MIT 6.837 Computer Graphics (Fall 2012)", "6-837-computer-graphics-fall-2012", ["notes:pages/lecture-notes/"]),
    "6.801": ("MIT 6.801 Machine Vision (Fall 2020)", "6-801-machine-vision-fall-2020", ["notes:pages/lecture-notes/"]),
    "6.0002": ("MIT 6.0002 Introduction to Computational Thinking and Data Science (Fall 2016)", "6-0002-introduction-to-computational-thinking-and-data-science-fall-2016", ["videos:video_galleries/lecture-videos/"]),
    "6.0001": ("MIT 6.0001 Introduction to Computer Science and Programming in Python (Fall 2016)", "6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016", ["videos:video_galleries/lecture-videos/"]),
    "6.830": ("MIT 6.830 Database Systems (Fall 2010)", "6-830-database-systems-fall-2010", ["notes:pages/lecture-notes/"]),
    "6.087": ("MIT 6.087 Practical Programming in C (IAP 2010)", "6-087-practical-programming-in-c-january-iap-2010", ["notes:pages/lecture-notes/"]),
    "6.S096": ("MIT 6.S096 Effective Programming in C and C++ (IAP 2014)", "6-s096-effective-programming-in-c-and-c-january-iap-2014", ["notes:pages/lecture-notes/"]),
    "6.035": ("MIT 6.035 Computer Language Engineering (Spring 2010)", "6-035-computer-language-engineering-spring-2010", ["notes:pages/lecture-notes/"]),
    "6.005": ("MIT 6.005 Software Construction (Spring 2016)", "6-005-software-construction-spring-2016", ["notes:pages/readings/"]),
    "6.004": ("MIT 6.004 Computation Structures (Spring 2017)", "6-004-computation-structures-spring-2017", ["chapters:pages/c"]),
    "6.828": ("MIT 6.828 Operating System Engineering (Fall 2012)", "6-828-operating-system-engineering-fall-2012", ["notes:pages/lecture-notes-and-readings/"]),
    "6.858": ("MIT 6.858 Computer Systems Security (Fall 2014)", "6-858-computer-systems-security-fall-2014", ["videos:video_galleries/video-lectures/"]),
    "MAS.S62": ("MIT MAS.S62 Cryptocurrency Engineering and Design (Spring 2018)", "mas-s62-cryptocurrency-engineering-and-design-spring-2018", ["videos:video_galleries/lecture-videos/"]),
    "6.829": ("MIT 6.829 Computer Networks (Fall 2002)", "6-829-computer-networks-fall-2002", ["notes:pages/lecture-notes/"]),
    "6.033": ("MIT 6.033 Computer System Engineering (Spring 2018)", "6-033-computer-system-engineering-spring-2018", ["pages:pages/week-"]),
    "6.170": ("MIT 6.170 Software Studio (Spring 2013)", "6-170-software-studio-spring-2013", ["notes:pages/lecture-notes/"]),
    "8.01": ("MIT 8.01SC Classical Mechanics (Fall 2016)", "8-01sc-classical-mechanics-fall-2016", ["pages:pages/week-"]),
    "6.002": ("MIT 6.002 Circuits and Electronics (Spring 2007)", "6-002-circuits-and-electronics-spring-2007", ["videos:video_galleries/video-lectures/"]),
    "6.003": ("MIT 6.003 Signals and Systems (Fall 2011)", "6-003-signals-and-systems-fall-2011", ["videos:video_galleries/lecture-videos/"]),
    "6.02": ("MIT 6.02 Introduction to EECS II: Digital Communication Systems (Fall 2012)", "6-02-introduction-to-eecs-ii-digital-communication-systems-fall-2012", ["videos:video_galleries/lecture-videos/"]),
}


def get(url: str) -> str:
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "study-app-lecture-catalog"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # network hiccups: retry with backoff
            if attempt == 3:
                print(f"  failed {url}: {e}", file=sys.stderr)
                return ""
            time.sleep(2 ** attempt)
    return ""


def text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def videos(page: str) -> list[dict]:
    out = []
    for href, title in re.findall(r'<a class="video-link" href="([^"]+)">.*?<h5 class="video-title">(.*?)</h5>', page, re.S):
        out.append({"title": text(title), "url": OCW + href, "kind": "video"})
    return out


def clean(t: str) -> str:
    t = re.sub(r"\s*\(\s*(PDF|PPT|PPTX|ZIP|CC|MS)[^)]*\)", "", t)
    return re.sub(r"\s+", " ", t).strip(" -·:")


def notes(page: str, slug: str) -> list[dict]:
    """Rows of the lecture table: a title, the row's full text (used for matching) and its first link."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [clean(text(c)) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        links = re.findall(rf'href="(/(?:courses/{re.escape(slug)}|ans7870)/[^"]+)"[^>]*>(.*?)</a>', row, re.S)
        if not links or len(cells) < 2:
            continue
        link_text = clean(text(links[0][1]))
        if re.match(r"^\d+\s*:", link_text):          # "1: Static Checking" style readings
            title = re.sub(r"^\d+\s*:\s*", "", link_text)
        else:
            body = [c for c in cells if c and not re.fullmatch(r"(L|Lec|Lecture|Ses|Session)?\s*[\d.]+", c)]
            title = body[0] if body else ""
        title = re.sub(r"^Lecture \d+:\s*", "", title)
        if len(title) > 110:
            title = title[:107].rsplit(" ", 1)[0] + "…"
        if title and not re.fullmatch(r"[\d\s]+", title) and not re.search(r"^(tutorial|quiz|exam|review|T\d+$)", title, re.I):
            out.append({"title": title, "about": " ".join(cells), "url": OCW + links[0][0], "kind": "notes"})
    return out


def chapters(home: str, slug: str, prefix: str) -> list[dict]:
    """6.004 style: numbered chapters, each with a "Topic Videos" page."""
    out = []
    for num, label in re.findall(rf'href="/courses/{re.escape(slug)}/{re.escape(prefix)}(\d+)/"[^>]*>(.*?)</a>', home, re.S):
        t = text(label)
        m = re.match(r"^(\d+)\s+(.+)$", t)
        if m and not any(o["num"] == num for o in out):
            out.append({"num": num, "title": m.group(2), "url": f"{OCW}/courses/{slug}/{prefix}{num}/c{num}s2/", "kind": "video"})
    for o in out:
        o.pop("num")
    return out


def deep_learning(url: str) -> list[dict]:
    page = get(url)
    out = []
    for block in re.findall(r"<!-- Lecture \d+ -->(.*?)<!-- end of Lecture", page, re.S):
        title = re.search(r'<h5 class="card-title">(.*?)</h5>', block, re.S)
        live = re.sub(r"<!--.*?-->", "", block, flags=re.S)
        video = re.search(r"href=[\"'](https://www\.youtube\.com/watch[^\"']+)[\"']>Video", live)
        slides = re.search(r"href=[\"']([^\"']+\.pdf)[\"']>Slides", live)
        if title and (video or slides):
            link = video.group(1) if video else url + slides.group(1)
            out.append({"title": text(title.group(1)).replace("</highlight", "").strip(), "url": html.unescape(link), "kind": "video" if video else "notes"})
    return out


def cs50(url: str) -> list[dict]:
    home = get(url)
    out = []
    for path in dict.fromkeys(re.findall(r'href="(weeks/[^"/]+/)"', home)):
        page = get(url + path)
        m = re.search(r"<title>(.*?) - CS50x", page)
        if m:
            t = re.sub(r"^Week \d+\s*", "", text(m.group(1))) or text(m.group(1))
            out.append({"title": t, "url": url + path, "kind": "video"})
    return out


def pages(home: str, slug: str, prefix: str) -> list[dict]:
    out, seen = [], set()
    for href, label in re.findall(rf'<a[^>]+href="(/courses/{re.escape(slug)}/{re.escape(prefix)}[^"]*)"[^>]*>(.*?)</a>', home, re.S):
        t = text(label)
        if href in seen or not t or re.search(r"assignment|exam|introduction$|ps[\s.-]?\d|problem set|^lecture \d+ outline$|calendar|worked example", t, re.I):
            continue
        seen.add(href)
        if prefix == "pages/week-" and slug.startswith("8-01") and not t.startswith("Lesson"):
            continue                                    # 8.01: lessons, not the week overviews
        t = re.sub(r"^(Lesson \d+|Week \d+):\s*", "", t)
        t = re.sub(r"\s*\[[\d.\-– ]+\]$", "", t)
        # the page's own description helps match broad titles like "Networking II"
        body = get(OCW + href)
        main = re.search(r'<main[^>]*>(.*?)</main>', body, re.S) or re.search(r'id="course-content-section"(.*?)</section>', body, re.S)
        full = text(main.group(1)) if main else ""
        about = full[:800]
        named = re.findall(r"Lecture \d+: (.+?) Lecture \d+ Outline", full)
        if named:                                       # 6.033 weeks: "Networking II: Routing (BGP); …"
            t = f"{t}: {'; '.join(dict.fromkeys(named))}"
        out.append({"title": t, "about": about, "url": OCW + href, "kind": "lesson"})
    return out


def main() -> None:
    catalog = {}
    for cid, (title, slug, sections) in COURSES.items():
        base = f"{OCW}/courses/{slug}/" if slug else sections[0].split(":", 1)[1]
        lectures = []
        for section in sections:
            kind, path = section.split(":", 1)
            if kind == "dl":
                lectures += deep_learning(path)
            elif kind == "cs50":
                lectures += cs50(path)
            elif kind == "chapters":
                lectures += chapters(get(base), slug, path)
            elif kind == "videos":
                lectures += videos(get(base + path))
            elif kind == "notes":
                lectures += notes(get(base + path), slug)
            else:
                lectures += pages(get(base), slug, path)
        seen, unique = set(), []
        for l in lectures:
            if l["url"] not in seen:
                seen.add(l["url"])
                unique.append(l)
        catalog[cid] = {"title": title, "url": base, "lectures": unique}
        print(f"{cid:8} {len(unique):3} lectures  {title}")
    out = ROOT / "data" / "lecture_catalog.json"
    out.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
