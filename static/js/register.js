const HINTS = {
  STUDENT: {
    label: "Student ID",
    placeholder: "Type a student ID or name…",
    hint: "Start typing to search registered students.",
  },
  FACULTY: {
    label: "Employee ID",
    placeholder: "Type an employee ID or name…",
    hint: "Start typing to search registered faculty.",
  },
  EXTERNAL: {
    label: "Reference",
    placeholder: "Type a reference or name…",
    hint: "Search for a registered external visitor.",
  },
};

const group = document.getElementById("visitor-type-group");
const form = document.getElementById("registration-form");
if (group && form) {
  const radios = Array.from(group.querySelectorAll('input[type="radio"]'));
  const panels = Array.from(document.querySelectorAll("[data-panel]"));
  const banners = Array.from(document.querySelectorAll("[data-banner]"));
  const identifier = form.querySelector("#id_identifier");
  const identifierLabel = form.querySelector('label[for="id_identifier"]');
  const identifierHint = document.getElementById("identifier-hint");
  const submitLabel = document.getElementById("register-submit-label");

  const SAVE_LABELS = {
    STUDENT: "Save Student",
    FACULTY: "Save Faculty",
    EXTERNAL: "Save External Visitor",
  };

  const currentType = () => radios.find((radio) => radio.checked)?.value || "STUDENT";

  function labelFor(type) {
    const key = `label${type.charAt(0)}${type.slice(1).toLowerCase()}`;
    return submitLabel?.dataset?.[key] || SAVE_LABELS[type] || "";
  }

  function applyType(type, { focus = false } = {}) {
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.panel !== type;
    });
    banners.forEach((banner) => {
      banner.hidden = banner.dataset.banner !== type;
    });
    radios.forEach((radio) => {
      radio.closest(".segment")?.classList.toggle("is-active", radio.checked);
    });

    if (submitLabel) {
      submitLabel.textContent = labelFor(type);
    }

    const copy = HINTS[type] || HINTS.STUDENT;
    if (identifierLabel) {
      identifierLabel.textContent = type === "EXTERNAL" ? "Reference (optional)" : copy.label;
      if (identifierLabel.querySelector(".req")) identifierLabel.querySelector(".req").remove();
      if (type !== "EXTERNAL") {
        const required = document.createElement("span");
        required.className = "req";
        required.setAttribute("aria-hidden", "true");
        required.textContent = "*";
        identifierLabel.appendChild(required);
      }
    }
    if (identifier) {
      identifier.placeholder = type === "EXTERNAL" ? "Generated automatically if blank" : `e.g. ${type === "FACULTY" ? "EMP-2024" : "2024-00123"}`;
      identifier.setAttribute("aria-required", type === "EXTERNAL" ? "false" : "true");
      if (focus) identifier.focus();
    }
    if (identifierHint) {
      identifierHint.textContent =
        type === "EXTERNAL"
          ? "External visitors receive an automatic reference number if you leave this blank."
          : type === "FACULTY"
            ? "The employee ID is used to look up this person during visit logging."
            : "The student ID is used to look up this person during visit logging.";
    }
  }

  radios.forEach((radio) => {
    radio.addEventListener("change", () => applyType(currentType(), { focus: false }));
  });

  applyType(currentType());
}
