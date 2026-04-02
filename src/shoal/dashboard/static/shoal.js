/* Shoal Dashboard — minimal client-side logic */
(function () {
  "use strict";

  /* ---- Tab switching ---- */
  function initTabs() {
    document.querySelectorAll(".tab-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var panel = btn.closest(".tab-panel-group");
        if (!panel) return;

        panel.querySelectorAll(".tab-btn").forEach(function (b) {
          b.classList.remove("active");
        });
        panel.querySelectorAll(".tab-content").forEach(function (c) {
          c.classList.remove("active");
        });

        btn.classList.add("active");
        var target = document.getElementById(btn.dataset.tab);
        if (target) target.classList.add("active");
      });
    });
  }

  /* ---- Keyboard shortcuts ---- */
  function initKeyboard() {
    document.addEventListener("keydown", function (e) {
      // / → focus search input
      if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
        e.preventDefault();
        var search = document.querySelector(".search-input");
        if (search) search.focus();
      }
      // Escape → blur focused input
      if (e.key === "Escape") {
        if (document.activeElement && document.activeElement.blur) {
          document.activeElement.blur();
        }
      }
    });
  }

  /* ---- Relative time auto-refresh ---- */
  function updateRelativeTimes() {
    document.querySelectorAll("[data-abs-time]").forEach(function (el) {
      var abs = el.getAttribute("data-abs-time");
      if (!abs) return;
      var dt = new Date(abs);
      var delta = Math.floor((Date.now() - dt.getTime()) / 1000);
      var text;
      if (delta < 60) text = "just now";
      else if (delta < 3600) text = Math.floor(delta / 60) + "m ago";
      else if (delta < 86400) text = Math.floor(delta / 3600) + "h ago";
      else text = Math.floor(delta / 86400) + "d ago";
      el.textContent = text;
    });
  }

  /* ---- Init ---- */
  document.addEventListener("DOMContentLoaded", function () {
    initTabs();
    initKeyboard();
    setInterval(updateRelativeTimes, 30000);

    // Re-init tabs after HTMX swaps
    document.body.addEventListener("htmx:afterSwap", function () {
      initTabs();
    });
  });
})();
