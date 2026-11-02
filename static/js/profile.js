const printButton = document.getElementById("print-qr");

if (printButton) {
  printButton.addEventListener("click", () => window.print());
}
