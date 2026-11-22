// "How did it go?" after a past paper: score, time taken, and the units that went badly.
// Units ticked here show up in Needs attention until their topics reach Confident.
import { savePracticeResult } from "./api.js";
import { esc, toast } from "./util.js";

// exam: { id, title, score, minutes, weak_units, unit_ids }; units: [{ id, name }] for the subject.
// Resolves to the saved result, or null if skipped.
export function openPaperResult(exam, units) {
  const covered = exam.unit_ids?.length ? units.filter((u) => exam.unit_ids.includes(u.id)) : units;
  const weak = new Set(exam.weak_units || []);
  const dlg = document.createElement("dialog");
  dlg.className = "practice paper-result";
  dlg.setAttribute("aria-labelledby", "pr-title");
  dlg.innerHTML = `
    <form class="pr-form">
      <div class="pr-head">
        <span class="pr-label">Past paper done</span>
        <h2 id="pr-title">How did it go?</h2>
        <p class="pr-exam">${esc(exam.title)}</p>
      </div>
      <div class="pr-fields">
        <label>Score
          <span class="pr-in"><input type="number" name="score" min="0" max="100" step="1" inputmode="numeric" value="${exam.score ?? ""}"> %</span></label>
        <label>Time taken
          <span class="pr-in"><input type="number" name="minutes" min="1" max="600" step="1" inputmode="numeric" value="${exam.minutes ?? ""}"> min</span></label>
      </div>
      ${covered.length ? `<fieldset class="pr-units">
        <legend>Units that went badly</legend>
        ${covered.map((u) => `<label><input type="checkbox" name="unit" value="${esc(u.id)}"${weak.has(u.id) ? " checked" : ""}> ${esc(u.name)}</label>`).join("")}
        <p class="pr-help">Their topics show up in Needs attention until you've raised them to Confident.</p>
      </fieldset>` : ""}
      <p class="pr-help">All optional. Leave anything blank you didn't track.</p>
      <div class="pr-actions">
        <button type="button" class="btn" data-pr="skip">Skip</button>
        <button type="submit" class="btn primary">Save</button>
      </div>
    </form>`;
  document.body.append(dlg);
  return new Promise((resolve) => {
    let result = null;
    dlg.addEventListener("close", () => { dlg.remove(); resolve(result); });
    dlg.querySelector('[data-pr="skip"]').addEventListener("click", () => dlg.close());
    dlg.querySelector("form").addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const fd = new FormData(e.target);
      const num = (name) => (fd.get(name) === "" ? null : Number(fd.get(name)));
      try {
        result = await savePracticeResult(exam.id, { score: num("score"), minutes: num("minutes"), weak_units: fd.getAll("unit") });
        dlg.close();
      } catch (err) {
        toast(`Couldn't save: ${err.message}`, true);
      }
    });
    dlg.showModal();
    dlg.querySelector('input[name="score"]').focus();
  });
}

// One line describing a paper's result, or "" if none was recorded.
export function resultText(exam, unitNames = {}) {
  const parts = [];
  if (exam.score != null) parts.push(`${exam.score}%`);
  if (exam.minutes != null) parts.push(`${exam.minutes} min`);
  if (exam.weak_units?.length) parts.push(`went badly: ${exam.weak_units.map((u) => unitNames[u] || u).join(", ")}`);
  return parts.join(" · ");
}
