const ICONS = {
  success: "check",
  error: "alert",
  warning: "alert",
  info: "info",
};

const TONE_ALIASES = {
  success: "success",
  error: "error",
  warning: "warning",
  info: "info",
  debug: "info",
};

function stack() {
  return document.getElementById("toast-stack");
}

export function dismissToast(element) {
  if (!element || element.classList.contains("is-leaving")) return;
  element.classList.add("is-leaving");
  window.setTimeout(() => element.remove(), 220);
}

export function toast(message, tone = "info", { timeout = 4500 } = {}) {
  const container = stack();
  if (!container) return null;

  const safeTone = TONE_ALIASES[tone] || "info";
  const element = document.createElement("div");
  element.className = `toast toast-${safeTone}`;
  element.setAttribute("role", safeTone === "error" ? "alert" : "status");

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${ICONS[safeTone]}`);
  svg.appendChild(use);

  const text = document.createElement("span");
  text.textContent = message;

  element.append(svg, text);
  element.addEventListener("click", () => dismissToast(element));
  container.appendChild(element);

  if (timeout > 0) window.setTimeout(() => dismissToast(element), timeout);
  return element;
}
