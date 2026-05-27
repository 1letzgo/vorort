/*
 * kalender-nav.js — Dropdown-Navigation für Termine / Aufgaben / Admin.
 *
 * Pro Seite gibt es einen Container [data-kalnav] mit ein oder zwei Dropdowns:
 *   - data-kalnav-trigger="ov"     -> wechselt Panel + URL ?tab=
 *   - data-kalnav-trigger="gruppe" -> voller Reload mit URL ?gruppe=
 *
 * Panels und Toolbar-Panel werden weiterhin über data-tab / data-toolbar-tab
 * gefunden, wie zuvor in den Inline-Skripten der Templates.
 *
 * Keyboard: Esc schließt; Pfeil oben/unten + Enter/Space im offenen Menü
 * navigieren / selektieren. Außenklick schließt.
 */
(function () {
  "use strict";

  function closeAllExcept(except) {
    document.querySelectorAll("[data-kalnav] .kalender-nav-dd__btn[aria-expanded='true']").forEach(function (btn) {
      if (btn === except) return;
      btn.setAttribute("aria-expanded", "false");
      var menu = btn.parentElement.querySelector(".kalender-nav-dd__menu");
      if (menu) menu.setAttribute("hidden", "");
    });
  }

  function openMenu(btn) {
    var menu = btn.parentElement.querySelector(".kalender-nav-dd__menu");
    if (!menu) return;
    closeAllExcept(btn);
    btn.setAttribute("aria-expanded", "true");
    menu.removeAttribute("hidden");
    var sel = menu.querySelector(".kalender-nav-dd__opt.is-active") || menu.querySelector(".kalender-nav-dd__opt");
    if (sel) sel.focus();
  }

  function closeMenu(btn) {
    var menu = btn.parentElement.querySelector(".kalender-nav-dd__menu");
    if (!menu) return;
    btn.setAttribute("aria-expanded", "false");
    menu.setAttribute("hidden", "");
  }

  function setOvLabel(container, id) {
    var trigger = container.querySelector("[data-kalnav-trigger='ov']");
    if (!trigger) return;
    var menu = trigger.parentElement.querySelector(".kalender-nav-dd__menu");
    if (!menu) return;
    var opt = menu.querySelector(".kalender-nav-dd__opt[data-value='" + cssEsc(id) + "']");
    var label = opt ? opt.querySelector(".kalender-nav-dd__opt-label").textContent : id;
    var btnVal = trigger.querySelector(".kalender-nav-dd__btn-val");
    if (btnVal) btnVal.textContent = label;
    // Badge im Trigger nachziehen, falls Option eine hat.
    var btnMain = trigger.querySelector(".kalender-nav-dd__btn-main");
    if (btnMain) {
      var oldBadge = btnMain.querySelector(".kalender-nav-dd__btn-badge");
      if (oldBadge) oldBadge.parentNode.removeChild(oldBadge);
      var optBadge = opt ? opt.querySelector(".kalender-nav-dd__opt-badge") : null;
      if (optBadge) {
        var b = document.createElement("span");
        b.className = "kalender-nav-dd__btn-badge";
        b.setAttribute("aria-label", optBadge.getAttribute("aria-label") || "");
        b.textContent = optBadge.textContent;
        btnMain.appendChild(b);
      }
    }
    menu.querySelectorAll(".kalender-nav-dd__opt").forEach(function (li) {
      var active = li.getAttribute("data-value") === id;
      li.classList.toggle("is-active", active);
      li.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function cssEsc(v) {
    return String(v).replace(/[^a-zA-Z0-9_-]/g, function (c) {
      return "\\" + c;
    });
  }

  function activateOv(container, id) {
    if (!id) return;
    var panels = {};
    document.querySelectorAll(".termin-tab-panel").forEach(function (p) {
      var pid = p.getAttribute("data-tab");
      if (pid) panels[pid] = p;
    });
    if (!panels[id]) return;
    Object.keys(panels).forEach(function (key) {
      var p = panels[key];
      if (!p) return;
      if (key === id) p.removeAttribute("hidden");
      else p.setAttribute("hidden", "");
    });
    var toolbars = {};
    document.querySelectorAll(".termin-toolbar-panel").forEach(function (el) {
      var tid = el.getAttribute("data-toolbar-tab");
      if (tid) toolbars[tid] = el;
    });
    Object.keys(toolbars).forEach(function (key) {
      var tb = toolbars[key];
      if (!tb) return;
      if (key === id) tb.removeAttribute("hidden");
      else tb.setAttribute("hidden", "");
    });
    setOvLabel(container, id);
    try {
      var u = new URL(window.location.href);
      var gruppeKeep = u.searchParams.get("gruppe");
      var gruppeActive = container.getAttribute("data-gruppe-active") || "alle";
      if (gruppeKeep === null || gruppeKeep === "") gruppeKeep = gruppeActive;
      u.searchParams.set("tab", id);
      if (gruppeKeep === "alle") u.searchParams.delete("gruppe");
      else u.searchParams.set("gruppe", gruppeKeep);
      history.replaceState({}, "", u.pathname + u.search + u.hash);
    } catch (e) {}
  }

  function activateGruppe(container, id) {
    if (!id) return;
    var defaultTab = container.getAttribute("data-default-tab") || "";
    try {
      var u = new URL(window.location.href);
      if (id === "alle") u.searchParams.delete("gruppe");
      else u.searchParams.set("gruppe", id);
      if (defaultTab && !u.searchParams.get("tab")) {
        u.searchParams.set("tab", defaultTab);
      }
      window.location.href = u.toString();
    } catch (e) {}
  }

  function onOptClick(container, kind, opt) {
    var val = opt.getAttribute("data-value");
    var btn = container.querySelector("[data-kalnav-trigger='" + kind + "']");
    if (btn) closeMenu(btn);
    if (kind === "ov") {
      activateOv(container, val);
      if (btn) btn.focus();
    } else if (kind === "gruppe") {
      activateGruppe(container, val);
    }
  }

  function onKey(e, container) {
    var open = container.querySelector(".kalender-nav-dd__btn[aria-expanded='true']");
    if (!open) return;
    var menu = open.parentElement.querySelector(".kalender-nav-dd__menu");
    if (!menu) return;
    var opts = Array.prototype.slice.call(menu.querySelectorAll(".kalender-nav-dd__opt"));
    var idx = opts.indexOf(document.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      closeMenu(open);
      open.focus();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      var next = opts[Math.min(opts.length - 1, idx + 1)] || opts[0];
      if (next) next.focus();
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      var prev = opts[Math.max(0, idx - 1)] || opts[opts.length - 1];
      if (prev) prev.focus();
      return;
    }
    if ((e.key === "Enter" || e.key === " ") && idx >= 0) {
      e.preventDefault();
      var kind = open.getAttribute("data-kalnav-trigger");
      onOptClick(container, kind, opts[idx]);
    }
  }

  function init(container) {
    container.querySelectorAll(".kalender-nav-dd__btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var open = btn.getAttribute("aria-expanded") === "true";
        if (open) closeMenu(btn);
        else openMenu(btn);
      });
    });
    container.querySelectorAll(".kalender-nav-dd__opt").forEach(function (opt) {
      var kind = opt.closest(".kalender-nav-dd__group").querySelector("[data-kalnav-trigger]").getAttribute("data-kalnav-trigger");
      opt.addEventListener("click", function (e) {
        e.stopPropagation();
        onOptClick(container, kind, opt);
      });
    });
    container.addEventListener("keydown", function (e) { onKey(e, container); });

    // Initiale Aktivierung aus URL (?tab=…) — wie vorher in den Inline-Skripten.
    var defaultTab = container.getAttribute("data-default-tab");
    var hasOvDropdown = !!container.querySelector("[data-kalnav-trigger='ov']");
    if (hasOvDropdown) {
      var sp = new URLSearchParams(window.location.search);
      var req = sp.get("tab");
      var panels = {};
      document.querySelectorAll(".termin-tab-panel").forEach(function (p) {
        var pid = p.getAttribute("data-tab");
        if (pid) panels[pid] = p;
      });
      if (req && panels[req]) activateOv(container, req);
      else if (defaultTab) activateOv(container, defaultTab);
    }
  }

  function start() {
    document.querySelectorAll("[data-kalnav]").forEach(init);
    document.addEventListener("click", function () {
      closeAllExcept(null);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
