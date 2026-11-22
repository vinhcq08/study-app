// Shared navigation: marks the current page and runs the light / dark / auto theme switch.
const THEME_KEY = "theme";
const ORDER = ["system", "light", "dark"];
const LABEL = { system: "Auto", light: "Light", dark: "Dark" };

function currentTheme() {
  try { return localStorage.getItem(THEME_KEY) || "system"; } catch { return "system"; }
}

function applyTheme(theme) {
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
}

function renderToggle(btn) {
  const theme = currentTheme();
  btn.querySelector("span").textContent = LABEL[theme];
  btn.setAttribute("aria-label", `Theme: ${LABEL[theme]}. Switch theme`);
}

export function initNav(page) {
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === page) a.setAttribute("aria-current", "page");
  });

  const btn = document.getElementById("themeToggle");
  if (!btn) return;
  renderToggle(btn);
  btn.addEventListener("click", () => {
    const next = ORDER[(ORDER.indexOf(currentTheme()) + 1) % ORDER.length];
    try { localStorage.setItem(THEME_KEY, next); } catch { /* storage blocked */ }
    applyTheme(next);
    renderToggle(btn);
  });
}
