"""Build the GitHub Pages version of the app into a folder of static files.

The pages, CSS and JavaScript are copied as they are, except that index.html becomes a small
shell (scripts/pages_shell.html) that starts Python once and shows the pages in a frame; the
Today page moves to today.html. The Python code and data are copied too, and run in the
browser with Pyodide (see app/browser.py and static/js/browser-backend.js).

    python scripts/build_pages.py --pyodide path/to/pyodide --out _site

--pyodide is a folder from the official Pyodide release holding pyodide.mjs, the runtime
files and the package wheels listed in PYODIDE_PACKAGES (the Pages workflow downloads it).
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Pyodide packages the app needs (their own dependencies load automatically).
PYODIDE_PACKAGES = ["sqlite3", "pydantic", "anyio", "idna"]
PYODIDE_RUNTIME = ["pyodide.mjs", "pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
                   "python_stdlib.zip", "pyodide-lock.json"]
# Pure-Python packages that Pyodide doesn't include, pinned to match requirements.txt.
EXTRA_WHEELS = ["fastapi==0.115.6", "starlette==0.41.3"]


def build(pyodide_dir: Path, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "static", out)
    (out / "js" / "config.js").write_text('export const BACKEND = "browser";\n', encoding="utf-8")
    # index.html becomes a shell that starts Python once and shows the pages in a frame,
    # so the Today page moves to today.html and links to "./" point there.
    (out / "index.html").rename(out / "today.html")
    for page in out.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        page.write_text(text.replace('href="./"', 'href="today.html"'), encoding="utf-8")
    shutil.copy2(ROOT / "scripts" / "pages_shell.html", out / "index.html")
    (out / ".nojekyll").write_text("", encoding="utf-8")  # serve every file as is

    # Pyodide runtime and the package wheels it needs
    lock = json.loads((pyodide_dir / "pyodide-lock.json").read_text(encoding="utf-8"))["packages"]
    norm = lambda name: name.lower().replace("_", "-")  # noqa: E731
    needed, queue = set(), list(PYODIDE_PACKAGES)
    while queue:
        name = norm(queue.pop())
        if name not in needed:
            needed.add(name)
            queue.extend(lock[name].get("depends", []))
    target = out / "pyodide"
    target.mkdir()
    for name in PYODIDE_RUNTIME + sorted(lock[n]["file_name"] for n in needed):
        shutil.copy2(pyodide_dir / name, target / name)

    # The app's Python code and data
    py = out / "py"
    files = []
    for src in sorted((ROOT / "app").rglob("*.py")) + sorted((ROOT / "data").glob("*.json")):
        rel = src.relative_to(ROOT).as_posix()
        (py / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, py / rel)
        files.append(rel)

    wheels_dir = py / "wheels"
    wheels_dir.mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "pip", "download", "--quiet", "--no-deps", "--only-binary=:all:",
                    "--dest", str(wheels_dir), *EXTRA_WHEELS], check=True)
    wheels = sorted(p.name for p in wheels_dir.glob("*.whl"))

    manifest = {"pyodide_packages": PYODIDE_PACKAGES, "wheels": wheels, "files": files}
    (py / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"Built {out} ({size:.1f} MB): {len(files)} source files, {len(wheels)} extra wheels, "
          f"{len(needed)} Pyodide packages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pyodide", type=Path, required=True, help="folder with the Pyodide release files")
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    build(args.pyodide.resolve(), args.out.resolve())
