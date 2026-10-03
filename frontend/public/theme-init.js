// Applies the saved colour theme before the app renders, avoiding a flash of
// the wrong theme. Kept as a file because the CSP forbids inline scripts.
(function () {
  try {
    var choice = localStorage.getItem("famtree-theme") || "system";
    var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme =
      choice === "system" ? (prefersDark ? "dark" : "light") : choice;
  } catch (e) {
    document.documentElement.dataset.theme = "light";
  }
})();
