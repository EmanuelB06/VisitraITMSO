import { dismissToast } from "./ui.js";

/* Auto-dismiss server-rendered flash messages. */
document.querySelectorAll(".toast[data-autohide]").forEach((element) => {
  element.addEventListener("click", () => dismissToast(element));
  window.setTimeout(() => dismissToast(element), 5000);
});

/* Topbar: mobile navigation toggle. */
const topbar = document.querySelector(".topbar");
const navToggle = topbar?.querySelector(".nav-toggle");
const nav = topbar?.querySelector(".nav");

if (topbar && navToggle && nav) {
  const setOpen = (open) => {
    nav.classList.toggle("is-open", open);
    navToggle.setAttribute("aria-expanded", String(open));
  };
  const isOpen = () => navToggle.getAttribute("aria-expanded") === "true";

  navToggle.addEventListener("click", () => setOpen(!isOpen()));

  /* Close after following a link or signing out. */
  nav.addEventListener("click", (event) => {
    if (event.target.closest("a, button[type='submit']")) setOpen(false);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen()) {
      setOpen(false);
      navToggle.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (isOpen() && !topbar.contains(event.target)) setOpen(false);
  });

  const desktop = window.matchMedia("(min-width: 901px)");
  desktop.addEventListener("change", (event) => {
    if (event.matches) setOpen(false);
  });
}

/* Topbar: deepen the shadow once the page scrolls. */
if (topbar) {
  const syncScrollState = () => topbar.classList.toggle("is-scrolled", window.scrollY > 4);
  syncScrollState();
  window.addEventListener("scroll", syncScrollState, { passive: true });
}

/* Ask before destructive form submissions (delete record, sign out is safe). */
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const message = form.dataset.confirm || "Are you sure?";
    if (!window.confirm(message)) event.preventDefault();
  });
});
