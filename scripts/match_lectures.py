"""Link lectures from data/lecture_catalog.json to the topics in data/topics.json.

Each subject draws on one or more open courses (SUBJECT_COURSES). A topic is linked to the lecture
whose title and description share the most meaningful words with the topic (weighted by how rare the
words are), with a small nudge for lectures at a similar point in the course. Matches below a
threshold are left out rather than guessed. data/lecture_overrides.json can pin or remove links by
hand; it wins over the automatic match.

    python scripts/match_lectures.py            # writes data/lectures.json
    python scripts/match_lectures.py --report   # also prints every match for review
"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import parse_topics  # noqa: E402

SUBJECT_COURSES = {
    "calc1": ["18.01"], "calc2": ["18.01", "18.02"], "mvc": ["18.02"], "opt": ["18.065"],
    "linalg": ["18.06", "18.065"], "de": ["18.03"], "toc": ["18.404"], "discrete": ["6.042"],
    "prob": ["6.041"], "daa": ["6.046", "6.006"], "ai": ["6.034", "CS50"], "ml": ["6.867", "6.034", "6.S191"],
    "dl": ["6.S191", "6.867"], "genai": ["6.S191"], "gfx": ["6.837"], "cv": ["6.801", "6.S191"],
    "sci": ["6.0002", "18.065"], "ds": ["6.0002", "CS50"], "db": ["6.830", "CS50"], "dbadmin": ["6.830"],
    "dblab": ["6.830", "CS50"], "cintro": ["CS50", "6.087"], "clang": ["6.087", "6.S096", "CS50"],
    "dsa": ["6.006", "CS50"], "compilers": ["6.035"], "python": ["6.0001", "CS50"], "oop": ["6.0001", "6.005"],
    "swc": ["6.005"], "ict": ["CS50", "6.033"], "arch": ["6.004"], "os": ["6.828", "6.033"],
    "sec": ["6.858", "6.033"], "chain": ["MAS.S62"], "archlab": ["6.004"], "net": ["6.02", "6.033", "6.829"],
    "csys": ["6.033"], "se": ["6.005", "6.170"], "sad": ["6.170", "6.005"], "sdm": ["6.005"],
    "web": ["6.170", "CS50"], "phys1": ["8.01"], "elec": ["6.002"], "dsp": ["6.003"], "comm": ["6.02"],
    "eleclab": ["6.002"], "embedded": ["6.004", "6.002"], "iot": ["6.02", "6.033"],
}
REVIEW = re.compile(r"\b(exam|quiz|final|course) review\b|review\b.*\b(exam|quiz)|^final review|problem session|next steps", re.I)
THRESHOLD = 0.30       # minimum similarity for a link
SECOND = 0.85          # a second lecture is kept if it scores at least this share of the best
POSITION_WEIGHT = 0.08

STOP = set("""a an and the of in on for to with by from as at is are be or vs via into using use its it
their your how what why when introduction intro basic basics overview part i ii iii iv v more cont
continued review lecture lectures notes week chapter lesson applications application example examples
problem problems simple general theory""".split())
SYNONYMS = {
    "matrices": "matrix", "vectors": "vector", "derivative": "differentiat", "derivatives": "differentiat",
    "differentiation": "differentiat", "integrals": "integral", "integration": "integral", "integrate": "integral",
    "eigenvalues": "eigen", "eigenvectors": "eigen", "eigenvalue": "eigen", "eigenvector": "eigen",
    "probabilities": "probability", "probabilistic": "probability", "graphs": "graph", "trees": "tree",
    "algorithms": "algorithm", "algorithmic": "algorithm", "neural": "neural", "networks": "network",
    "networking": "network", "learning": "learn", "functions": "function", "series": "series",
    "sequences": "sequence", "recursive": "recursion", "recurrences": "recurrence", "sorting": "sort",
    "hashing": "hash", "hashes": "hash", "pointers": "pointer", "arrays": "array", "strings": "string",
    "regular": "regular", "languages": "language", "grammars": "grammar", "transactions": "transaction",
    "queries": "query", "indexes": "index", "indexing": "index", "processes": "process", "threads": "thread",
    "scheduling": "schedul", "schedulers": "schedul", "circuits": "circuit", "signals": "signal",
    "systems": "system", "transforms": "transform", "fourier": "fourier", "convolutional": "convolution",
    "cnns": "convolution", "cnn": "convolution", "rnn": "sequence", "rnns": "sequence", "transformers": "transformer",
    "attention": "transformer", "generative": "generat", "generation": "generat", "gans": "generat",
    "vaes": "generat", "diffusion": "generat", "reinforcement": "reinforcement", "optimisation": "optimiz",
    "optimization": "optimiz", "optimizing": "optimiz", "minimization": "optimiz", "classes": "class",
    "objects": "object", "inheritance": "inherit", "polymorphism": "inherit", "tests": "test", "testing": "test",
    "specifications": "spec", "specification": "spec", "specs": "spec", "abstract": "abstract",
    "abstraction": "abstract", "concurrency": "concurren", "concurrent": "concurren", "locks": "lock",
    "locking": "lock", "caches": "cache", "caching": "cache", "pipelining": "pipelin", "pipelined": "pipelin",
    "memory": "memory", "encryption": "crypto", "cryptography": "crypto", "cryptographic": "crypto",
    "signatures": "signature", "blockchains": "blockchain", "bitcoin": "blockchain", "routing": "rout",
    "routers": "rout", "protocols": "protocol", "kinematics": "kinematic", "forces": "force", "momentum": "momentum",
    "rotational": "rotation", "torques": "torque", "oscillations": "oscillat", "oscillator": "oscillat",
    "induction": "induction", "proofs": "proof", "counting": "count", "combinatorics": "count",
    "permutations": "count", "combinations": "count", "machines": "machine", "automata": "automat",
    "automaton": "automat", "nfa": "automat", "dfa": "automat", "turing": "turing", "decidability": "decidab",
    "decidable": "decidab", "undecidable": "decidab", "variables": "random_variable", "variance": "variance",
    "expectation": "expect", "expected": "expect", "transistors": "transistor", "mosfet": "transistor",
    "amplifiers": "amplif", "amplifier": "amplif", "diodes": "diode", "capacitors": "capacit", "inductors": "inductor",
    "filters": "filter", "filtering": "filter", "sampling": "sampl", "samples": "sampl", "modulation": "modulat",
    "codes": "code", "coding": "code", "compression": "compress", "huffman": "compress", "entropy": "entropy",
    "regression": "regression", "classification": "classif", "classifiers": "classif", "clustering": "cluster",
    "kernels": "kernel", "svms": "svm", "svm": "svm", "boosting": "boost", "ensembles": "ensemble",
    "datasets": "data", "database": "database", "databases": "database", "relational": "relation",
    "relations": "relation", "normalization": "normal", "normalisation": "normal", "sql": "sql",
    "shaders": "shading", "shader": "shading", "rendering": "render", "rays": "ray", "raytracing": "ray",
    "textures": "texture", "animations": "animat", "animation": "animat", "splines": "spline", "curves": "curve",
    "images": "image", "cameras": "camera", "optical": "optic", "stereo": "stereo", "paging": "page",
    "pages": "page", "files": "file", "filesystems": "file", "virtual": "virtual", "interrupts": "interrupt",
    "attacks": "attack", "vulnerabilities": "attack", "exploits": "attack", "web": "web", "http": "web",
    "javascript": "web", "html": "web", "css": "web", "apis": "api", "rest": "api", "restful": "api",
    "git": "version_control", "versioning": "version_control", "requirements": "requirement",
    "debugging": "debug", "bugs": "debug", "exceptions": "exception", "loops": "loop", "iteration": "loop",
    "dictionaries": "dictionary", "lists": "list", "tuples": "tuple",
}


def stem(w: str) -> str:
    w = SYNONYMS.get(w, w)
    for suffix in ("ations", "ation", "ings", "ing", "ies", "es", "s", "ed"):
        if len(w) > 5 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower().replace("’", "'")):
        if w in STOP or len(w) < 2 or w.isdigit():
            continue
        out.append(stem(w))
    return out


def vector(tokens: list[str], idf: dict) -> dict:
    tf = Counter(tokens)
    v = {t: (1 + math.log(n)) * idf.get(t, 1.0) for t, n in tf.items()}
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {t: x / norm for t, x in v.items()}


def cosine(a: dict, b: dict) -> float:
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def main(report: bool) -> None:
    catalog = json.loads((ROOT / "data" / "lecture_catalog.json").read_text(encoding="utf-8"))
    topics_data = json.loads((ROOT / "data" / "topics.json").read_text(encoding="utf-8"))
    topics_data.pop("_about", None)
    overrides_file = ROOT / "data" / "lecture_overrides.json"
    raw = json.loads(overrides_file.read_text(encoding="utf-8")) if overrides_file.exists() else {}
    raw.pop("_about", None)
    # {"subject": {"Topic name": ["COURSE|title words", ...]}}; an empty list means no lecture
    from app.db import slugify
    overrides = {f"{sid}:{slugify(name)}": refs for sid, topics in raw.items() for name, refs in topics.items()}
    known = {f"{sid}:{slugify(n.lstrip('*').strip())}" for sid, units in topics_data.items() for _, names in units for n in names}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise SystemExit(f"Overrides name topics that don't exist: {unknown}")

    lectures = {}
    for cid, course in catalog.items():
        n = len(course["lectures"])
        for i, l in enumerate(course["lectures"]):
            lid = f"{cid}#{i + 1}"
            lectures[lid] = {**l, "id": lid, "course": cid, "pos": i / max(1, n - 1),
                             "review": bool(REVIEW.search(l["title"]))}

    def resolve(ref: str) -> str:
        """An override entry "COURSE|title words" names a lecture by its course and part of its title."""
        cid, _, needle = ref.partition("|")
        same = [lid for lid, l in lectures.items() if l["course"] == cid]
        for lid in same:                                 # an exact title first ("CS50|C"), then part of one
            if lectures[lid]["title"].lower() == needle.lower():
                return lid
        for lid in same:
            if needle.lower() in lectures[lid]["title"].lower():
                return lid
        raise SystemExit(f"Override {ref!r} matches no lecture")
    docs = {lid: words(l["title"] + " " + l["title"] + " " + l.get("about", "")) for lid, l in lectures.items()}
    df = Counter(t for toks in docs.values() for t in set(toks))
    idf = {t: math.log(1 + len(docs) / n) for t, n in df.items()}
    lvec = {lid: vector(toks, idf) for lid, toks in docs.items()}

    links, used, missing, total = {}, set(), [], 0
    for sid, units in topics_data.items():
        courses = SUBJECT_COURSES.get(sid, [])
        _, topic_rows = parse_topics(sid, units)
        unit_names = {f"{sid}:u{i + 1}": name for i, (name, _) in enumerate(units)}
        n = len(topic_rows)
        if report:
            print(f"\n=== {sid}  ({', '.join(courses) or 'no course'})")
        for k, t in enumerate(topic_rows):
            total += 1
            tvec = vector(words(t["name"] + " " + t["name"] + " " + unit_names[t["unit_id"]]), idf)
            tpos = k / max(1, n - 1)
            scored = []
            for rank, cid in enumerate(courses):
                for lid, l in lectures.items():
                    if l["course"] != cid or l["review"]:
                        continue
                    s = cosine(tvec, lvec[lid])
                    if s <= 0:
                        continue
                    if rank == 0:
                        s += POSITION_WEIGHT * (1 - abs(tpos - l["pos"]))
                    else:
                        s *= 0.92          # prefer the subject's main course
                    scored.append((s, lid))
            scored.sort(reverse=True)
            chosen = []
            if scored and scored[0][0] >= THRESHOLD:
                chosen.append(scored[0][1])
                if len(scored) > 1 and scored[1][0] >= max(THRESHOLD, SECOND * scored[0][0]):
                    chosen.append(scored[1][1])
            if t["id"] in overrides:
                chosen = [resolve(ref) for ref in overrides[t["id"]]]
            if chosen:
                links[t["id"]] = chosen
                used.update(chosen)
            else:
                missing.append(t["id"])
            if report:
                best = f"{scored[0][0]:.2f}" if scored else "-"
                shown = " + ".join(f"{lectures[c]['course']} {lectures[c]['title'][:48]}" for c in chosen) if chosen else "—"
                print(f"  [{best}] {t['name'][:44]:44} -> {shown}")

    courses_out = {cid: {"title": c["title"], "url": c["url"]} for cid, c in catalog.items()}
    lectures_out = [{k: l[k] for k in ("id", "course", "title", "url", "kind")} for lid, l in lectures.items() if lid in used]
    out = {
        "_about": "Open lectures linked to topics. Built by scripts/match_lectures.py from data/lecture_catalog.json; "
                  "pin or remove links by hand in data/lecture_overrides.json.",
        "courses": courses_out,
        "subject_courses": {sid: c for sid, c in SUBJECT_COURSES.items()},
        "lectures": lectures_out,
        "topics": links,
    }
    (ROOT / "data" / "lectures.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nLinked {len(links)} of {total} topics to {len(lectures_out)} lectures; {len(missing)} without a match.")


if __name__ == "__main__":
    main("--report" in sys.argv)
