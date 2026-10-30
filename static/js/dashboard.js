const filterForm = document.querySelector("[data-filter-form]");

if (filterForm) {
  const searchInput = filterForm.querySelector('input[type="search"]');
  const selects = Array.from(filterForm.querySelectorAll("select"));
  const dates = Array.from(filterForm.querySelectorAll('input[type="date"]'));

  let searchTimer = null;

  searchInput?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => filterForm.requestSubmit(), 450);
  });

  selects.forEach((select) => {
    select.addEventListener("change", () => filterForm.requestSubmit());
  });

  dates.forEach((input) => {
    input.addEventListener("change", () => filterForm.requestSubmit());
  });
}

/* Close the export menu when clicking elsewhere. */
document.querySelectorAll("details.export-menu").forEach((menu) => {
  document.addEventListener("click", (event) => {
    if (!menu.open) return;
    if (!menu.contains(event.target)) menu.open = false;
  });
});
