// Runs the app's Python API inside the browser with Pyodide (used by the GitHub Pages version).
// Your data is stored in this browser's IndexedDB, so it stays on this device.
// The Pages site's index.html (scripts/pages_shell.html) loads this once and shows each page
// in a frame; the pages' api.js reaches it through window.parent.studyBackend.
import { loadPyodide } from "../pyodide/pyodide.mjs";

const HOME = "/home/pyodide/study";
const DATA_DIR = "/study-app-data";
const base = (rel) => new URL(rel, import.meta.url).href;

let ready = null;
let writes = Promise.resolve();

function bootScreen(text) {
  let el = document.getElementById("boot");
  if (!el) {
    el = Object.assign(document.createElement("div"), { id: "boot", className: "boot", role: "status" });
    document.body.append(el);
  }
  el.innerHTML = text ? `<div class="boot-box"><span class="boot-spin" aria-hidden="true"></span><p>${text}</p></div>` : "";
  el.hidden = !text;
}

const sync = (py, populate) => new Promise((resolve, reject) =>
  py.FS.syncfs(populate, (err) => (err ? reject(err) : resolve())));

export function boot() {
  if (ready) return ready;
  ready = (async () => {
    let seen = false;
    try { seen = localStorage.getItem("study-app-booted") === "1"; } catch { /* storage blocked */ }
    bootScreen(seen ? "Opening Study App…"
      : "Starting Study App in your browser…<br><small>The first visit downloads about 19 MB. After that it opens much faster, and your progress is saved on this device.</small>");
    try {
      const py = await loadPyodide({ indexURL: base("../pyodide/") });
      const manifest = await (await fetch(base("../py/manifest.json"))).json();
      await py.loadPackage(manifest.pyodide_packages);
      await py.loadPackage(manifest.wheels.map((w) => base(`../py/wheels/${w}`)));
      for (const file of manifest.files) {
        const text = await (await fetch(base(`../py/${file}`))).text();
        const target = `${HOME}/${file}`;
        py.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
        py.FS.writeFile(target, text);
      }
      py.FS.mkdirTree(DATA_DIR);
      py.FS.mount(py.FS.filesystems.IDBFS, {}, DATA_DIR);
      await sync(py, true);
      py.runPython(`import sys\nsys.path.insert(0, "${HOME}")\nimport app.browser\napp.browser.start()`);
      await sync(py, false);
      bootScreen("");
      try { localStorage.setItem("study-app-booted", "1"); } catch { /* storage blocked */ }
      return py;
    } catch (err) {
      bootScreen(`Couldn't start the app: ${err.message}. Reload the page to try again.`);
      ready = null;
      throw err;
    }
  })();
  return ready;
}

// Returns plain values ({ status, text }) so pages in another frame can use the result safely.
export async function call(method, path, body = "") {
  const py = await boot();
  method = (method || "GET").toUpperCase();
  const handle = py.pyimport("app.browser").handle;
  const result = await handle(method, path, body || "");
  const [status, text] = result.toJs();
  result.destroy();
  handle.destroy();
  if (method !== "GET") {
    writes = writes.then(() => sync(py, false)).catch(() => {});
    await writes;
  }
  return { status, text };
}
